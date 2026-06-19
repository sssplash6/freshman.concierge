# scheduler.py
import html
import logging
import os
import re
from datetime import datetime, timedelta, date, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_e = html.escape

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.error import TelegramError

import database as db
import messages as msg

logger = logging.getLogger(__name__)
DEFAULT_TZ = os.getenv("TIMEZONE", "Asia/Tashkent")
TZ = pytz.timezone(DEFAULT_TZ)
# Sheet event times are authored in the team's zone; this is the source of truth
# for absolute event moments. Per-user zones only affect display and time-of-day
# nudges (see staff_tz / compute_reminder_dt).
SOURCE_TZ = TZ
_scheduler: AsyncIOScheduler | None = None


def staff_tz(staff: dict) -> pytz.BaseTzInfo:
    """The recipient's preferred zone, falling back to the team zone."""
    name = staff.get("timezone") or DEFAULT_TZ
    try:
        return pytz.timezone(name)
    except Exception:
        return SOURCE_TZ


def tz_label(dt: datetime) -> str:
    """Render a tz-aware datetime's UTC offset as 'GMT+5' / 'GMT+3' / 'GMT-4'."""
    off = dt.utcoffset() or timedelta(0)
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    h, m = divmod(abs(minutes), 60)
    return f"GMT{sign}{h}" + (f":{m:02d}" if m else "")


_TZ_OFFSET_RE = re.compile(r"^(?:gmt|utc)?\s*([+-]?\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def parse_timezone_input(text: str) -> str | None:
    """Resolve free-form user input to a canonical zone name, or None if unreadable.

    Accepts 'GMT+5', 'UTC+5', '+5', '5', 'gmt-3', and full IANA names like
    'Asia/Tashkent'. Whole-hour offsets only (returns 'UTC' or an 'Etc/GMT±N' zone
    that pytz can load and that displays as 'GMT±N').
    """
    s = (text or "").strip()
    if not s:
        return None
    if s.lower() in ("utc", "gmt"):
        return "UTC"
    # Named / IANA zone (e.g. 'Asia/Tashkent', 'UTC').
    try:
        pytz.timezone(s)
        return s
    except Exception:
        pass
    m = _TZ_OFFSET_RE.match(s)
    if not m:
        return None
    if int(m.group(2) or 0) != 0:
        return None  # only whole-hour offsets supported via typed entry
    hours = int(m.group(1))
    if not (-12 <= hours <= 14):
        return None
    if hours == 0:
        return "UTC"
    # Etc/GMT signs are inverted: Etc/GMT-5 == UTC+5.
    name = f"Etc/GMT{'-' if hours > 0 else '+'}{abs(hours)}"
    try:
        pytz.timezone(name)
        return name
    except Exception:
        return None


def tz_pretty(name: str) -> str:
    """Human label for a stored zone: 'GMT+5' for offsets, 'Asia/Tashkent (GMT+5)' for IANA."""
    label = tz_label(datetime.now(pytz.timezone(name)))
    if name == "UTC" or name.startswith("Etc/"):
        return label
    return f"{name} ({label})"


def event_instant(event: dict) -> datetime | None:
    """The absolute moment of a timed event, interpreted in the team source zone."""
    if not event.get("event_date") or not event.get("event_time"):
        return None
    d = date.fromisoformat(event["event_date"])
    h, m = map(int, event["event_time"].split(":"))
    return SOURCE_TZ.localize(datetime(d.year, d.month, d.day, h, m))

# (staff_name, day_of_week, reminder_hour, reminder_min, cohort, weekday_label, time_label)
_FIXED_SEMINARS = [
    ("Gulrukh", "wed", 17, 30, "April Offline", "Wednesday", "6:30 – 9:00 PM"),
    ("Rustam",  "wed", 18, 30, "April Online",  "Wednesday", "7:30 – 9:00 PM"),
    ("Gulrukh", "sat", 14,  0, "May Offline",   "Saturday",  "3:00 PM"),
    ("Rustam",  "thu", 18, 30, "May Online",    "Thursday",  "7:30 PM"),
]

_DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _next_weekday(dow: str) -> date:
    today = date.today()
    delta = (_DOW[dow] - today.weekday()) % 7
    return today + timedelta(days=delta or 7)  # if today, use next week


def fixed_seminar_events_for(staff_name: str) -> list[dict]:
    """Synthetic event dicts for the fixed seminars assigned to a staff member."""
    result = []
    for name, dow, _, _, cohort, weekday_label, time_label in _FIXED_SEMINARS:
        if name != staff_name:
            continue
        result.append({
            "type": "seminar",
            "cohort": cohort,
            "weekday_label": weekday_label,
            "time_label": time_label,
            "event_date": _next_weekday(dow).isoformat(),
            "staff_name": staff_name,
            "title": "Seminar",
            "id": None,
        })
    return result


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=TZ)
    return _scheduler


def compute_reminder_dt(event: dict, tz: pytz.BaseTzInfo | None = None) -> datetime | None:
    """When this event's reminder should fire, as a tz-aware datetime.

    Lecture reminders are anchored to the event's absolute moment (1 hour before)
    and are the same instant for everyone. Consultation reminders are a
    time-of-day nudge at 10:00 in the recipient's zone (``tz``, default source).
    """
    tz = tz or SOURCE_TZ
    if event["type"] == "lecture":
        inst = event_instant(event)
        return inst - timedelta(hours=1) if inst else None
    elif event["type"] == "consult":
        d_str = event.get("event_date") or event.get("week_start")
        if d_str:
            d = date.fromisoformat(d_str)
            return tz.localize(datetime(d.year, d.month, d.day, 10, 0))
    return None


def format_reminder_message(event: dict, tz: pytz.BaseTzInfo | None = None) -> str:
    """Format a reminder message string for the given event in the recipient's zone."""
    tz = tz or SOURCE_TZ
    if event["type"] == "lecture":
        inst = event_instant(event)
        if inst:
            local = inst.astimezone(tz)
            weekday = local.strftime("%A")
            datestr = local.strftime("%B %-d")
            timestr = local.strftime("%H:%M")
            label = tz_label(local)
        else:
            d = date.fromisoformat(event["event_date"])
            weekday = d.strftime("%A")
            datestr = d.strftime("%B %-d")
            timestr = "TBD"
            label = tz_label(tz.localize(datetime(d.year, d.month, d.day)))
        return msg.REMINDER_LECTURE.format(
            title=_e(event["title"]),
            cohort=_e(event["cohort"]),
            weekday=weekday,
            date=datestr,
            time=timestr,
            tz=label,
        )
    elif event["type"] == "consult":
        if event.get("event_date"):
            d = date.fromisoformat(event["event_date"])
            return msg.REMINDER_CONSULT_DATE.format(
                cohort=_e(event["cohort"]),
                weekday=d.strftime("%A"),
                date=d.strftime("%B %-d"),
                duration=event.get("duration_min") or "?",
            )
        else:
            d = date.fromisoformat(event["week_start"])
            return msg.REMINDER_CONSULT_WEEK.format(
                cohort=_e(event["cohort"]),
                date=d.strftime("%B %-d"),
                duration=event.get("duration_min") or "?",
            )
    elif event["type"] == "seminar":
        return msg.REMINDER_SEMINAR.format(
            cohort=_e(event["cohort"]),
            weekday=event.get("weekday_label", ""),
            time=event.get("time_label", ""),
        )
    raise ValueError(f"Unknown event type: {event['type']!r}")


def format_weekly_task_reminder(event: dict) -> str:
    d = date.fromisoformat(event["week_start"])
    return msg.WEEKLY_TASK_REMINDER.format(
        cohort=_e(event["cohort"]),
        title=_e(event["title"]),
        date=d.strftime("%B %-d"),
    )


async def send_weekly_task_reminders(bot: Bot) -> None:
    """Weekly Saturday 17:00 nudge (in each recipient's own zone) for pending weekly tasks.

    Runs on a 60-second interval; the per-staff local Saturday 17:00–17:30 window plus the
    once-per-day idempotency key keep it to a single send per task per week.
    """
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for staff in staff_list:
        now_local = datetime.now(staff_tz(staff))
        # Only fire during the recipient's local Saturday 17:00–17:30 window.
        if not (now_local.weekday() == 5 and now_local.hour == 17 and now_local.minute < 30):
            continue
        today = now_local.date()
        week_start_str = (today - timedelta(days=today.weekday())).isoformat()
        today_str = today.isoformat()

        for event in events:
            if not event.get("week_start") or event.get("event_date"):
                continue
            if event["week_start"] != week_start_str:
                continue
            if staff["display_name"] != event["staff_name"]:
                continue
            if await db.is_weekly_complete(staff["chat_id"], week_start_str, event["title"], event["cohort"]):
                continue
            if await db.weekly_reminder_sent_today(staff["chat_id"], today_str, event["title"], event["cohort"]):
                continue

            text = format_weekly_task_reminder(event)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Done", callback_data=f"wc:{event['id']}")
            ]])
            try:
                await bot.send_message(
                    chat_id=staff["chat_id"],
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                await db.log_weekly_reminder(staff["chat_id"], today_str, event["title"], event["cohort"])
                logger.info("Sent weekly task reminder for event %d to chat %d", event["id"], staff["chat_id"])
            except TelegramError as e:
                logger.error("Failed to send weekly reminder to %d: %s", staff["chat_id"], e)


async def send_seminar_reminder(
    bot: Bot, chat_id: int, cohort: str, weekday: str, time: str
) -> None:
    text = msg.REMINDER_SEMINAR.format(
        cohort=_e(cohort), weekday=weekday, time=time
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        logger.info("Sent seminar reminder to chat %d (%s %s)", chat_id, weekday, time)
    except TelegramError as e:
        logger.error("Failed to send seminar reminder to %d: %s", chat_id, e)


async def check_and_send_reminders(bot: Bot) -> None:
    """Check all events for due reminders and send them, per recipient's zone."""
    now = datetime.now(SOURCE_TZ)  # tz-aware; compares correctly against any zone
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        # Week-based consults (week_start + no event_date) are nudged as recurring
        # weekly tasks by send_weekly_task_reminders.
        if event.get("week_start") and not event.get("event_date"):
            continue

        for staff in staff_list:
            if staff["display_name"] != event["staff_name"]:
                continue
            tz = staff_tz(staff)
            reminder_dt = compute_reminder_dt(event, tz)
            if reminder_dt is None:
                continue
            # Fire if past reminder time and within a 30-minute grace window
            # (idempotency prevents duplicates).
            if not (reminder_dt <= now <= reminder_dt + timedelta(minutes=30)):
                continue
            if await db.reminder_already_sent(event["id"], staff["chat_id"]):
                continue
            try:
                text = format_reminder_message(event, tz)
            except Exception:
                logger.exception("Failed to format reminder for event %d", event["id"])
                break
            try:
                await bot.send_message(chat_id=staff["chat_id"], text=text, parse_mode="HTML")
                await db.log_reminder(event["id"], staff["chat_id"])
                logger.info(
                    "Sent reminder for event %d to chat %d", event["id"], staff["chat_id"]
                )
            except TelegramError as e:
                logger.error("Failed to send reminder to %d: %s", staff["chat_id"], e)


async def send_completion_checks(bot: Bot) -> None:
    """Send a Y/N completion check 2 hours after any timed event."""
    now = datetime.now(SOURCE_TZ)
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        inst = event_instant(event)
        if inst is None:
            continue
        check_dt = inst + timedelta(hours=2)  # absolute, same instant for everyone
        if not (check_dt <= now <= check_dt + timedelta(minutes=30)):
            continue

        icon = "🎓" if event["type"] == "lecture" else "📋"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"cc:yes:{event['id']}"),
            InlineKeyboardButton("❌ No",  callback_data=f"cc:no:{event['id']}"),
        ]])

        for staff in staff_list:
            if staff["display_name"] != event["staff_name"]:
                continue
            if await db.completion_prompt_sent(event["id"], staff["chat_id"]):
                continue
            local = inst.astimezone(staff_tz(staff))
            text = msg.COMPLETION_CHECK.format(
                icon=icon,
                title=_e(event["title"]),
                cohort=_e(event["cohort"]),
                date=f"{local.strftime('%A, %B %-d')} · {local.strftime('%H:%M')} {tz_label(local)}",
            )
            try:
                await bot.send_message(
                    chat_id=staff["chat_id"],
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                await db.mark_completion_prompt_sent(event["id"], staff["chat_id"])
                logger.info("Sent completion check for event %d to chat %d", event["id"], staff["chat_id"])
            except TelegramError as e:
                logger.error("Failed to send completion check to %d: %s", staff["chat_id"], e)


def format_task_deadline(deadline_iso: str, tz: pytz.BaseTzInfo) -> str:
    """Render a stored UTC deadline in the recipient's zone, e.g. 'Fri, Jun 5 · 18:00 GMT+5'."""
    dt = datetime.fromisoformat(deadline_iso).astimezone(tz)
    return f"{dt.strftime('%a, %b %-d')} · {dt.strftime('%H:%M')} {tz_label(dt)}"


async def check_task_deadlines(bot: Bot) -> None:
    """Send the pre-deadline reminder (~2h before) and the deadline check-in for custom tasks."""
    now = datetime.now(timezone.utc)
    tasks = await db.get_pending_tasks()
    staff_list = await db.get_all_staff()

    for task in tasks:
        deadline = datetime.fromisoformat(task["deadline"])
        recipients = [s for s in staff_list if s["display_name"] == task["staff_name"]]

        # Pre-deadline reminder: once, within the final 2 hours before the deadline.
        if not task["predeadline_sent"]:
            if now >= deadline:
                # Deadline already passed before we could remind — skip straight to check-in.
                await db.mark_task_flag(task["id"], "predeadline_sent")
            elif now >= deadline - timedelta(hours=2):
                for s in recipients:
                    text = msg.TASK_PREDEADLINE.format(
                        desc=_e(task["description"]),
                        deadline=format_task_deadline(task["deadline"], staff_tz(s)),
                    )
                    try:
                        await bot.send_message(chat_id=s["chat_id"], text=text, parse_mode="HTML")
                    except TelegramError as e:
                        logger.error("Failed to send task pre-deadline to %d: %s", s["chat_id"], e)
                await db.mark_task_flag(task["id"], "predeadline_sent")

        # Deadline check-in: once, at or after the deadline.
        if not task["checkin_sent"] and now >= deadline:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes", callback_data=f"tc:yes:{task['id']}"),
                InlineKeyboardButton("❌ No",  callback_data=f"tc:no:{task['id']}"),
            ]])
            for s in recipients:
                text = msg.TASK_CHECKIN.format(
                    desc=_e(task["description"]),
                    deadline=format_task_deadline(task["deadline"], staff_tz(s)),
                )
                try:
                    await bot.send_message(
                        chat_id=s["chat_id"], text=text, parse_mode="HTML", reply_markup=keyboard
                    )
                except TelegramError as e:
                    logger.error("Failed to send task check-in to %d: %s", s["chat_id"], e)
            await db.mark_task_flag(task["id"], "checkin_sent")


async def check_hw_completion_checks(bot: Bot) -> None:
    """3 days after each lecture, send the assigned TA a homework-check notification."""
    events = await db.get_all_events()
    ta_assignments = await db.get_all_ta_assignments()  # {cohort: ta_name}
    staff_list = await db.get_all_staff()

    for event in events:
        if event.get("type") not in ("lecture", "seminar"):
            continue
        if not event.get("event_date"):
            continue

        cohort = event["cohort"]
        ta_name = ta_assignments.get(cohort)
        if not ta_name:
            continue

        ta_staff = next((s for s in staff_list if s["display_name"] == ta_name), None)
        if not ta_staff:
            continue

        now_local = datetime.now(staff_tz(ta_staff))
        if not (now_local.hour == 10 and now_local.minute < 30):
            continue

        event_date = date.fromisoformat(event["event_date"])
        if now_local.date() != event_date + timedelta(days=3):
            continue

        if await db.hw_check_sent(cohort, event["event_date"], ta_staff["chat_id"]):
            continue

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"hw:yes:{event['id']}"),
            InlineKeyboardButton("❌ No",  callback_data=f"hw:no:{event['id']}"),
        ]])
        text = msg.HW_CHECK.format(
            cohort=_e(cohort),
            title=_e(event["title"]),
            date=event_date.strftime("%B %-d"),
        )
        try:
            await bot.send_message(
                chat_id=ta_staff["chat_id"],
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            await db.mark_hw_check_sent(cohort, event["event_date"], ta_staff["chat_id"])
            logger.info(
                "Sent HW check for event %d to TA %s (chat %d)",
                event["id"], ta_name, ta_staff["chat_id"],
            )
        except TelegramError as e:
            logger.error("Failed to send HW check to TA %s: %s", ta_name, e)


async def send_weekly_consult_links(bot: Bot) -> None:
    """Every Monday: post each staff member's consultation link to the relevant group chat."""
    today = datetime.now(TZ).date()
    week_start_str = today.isoformat()

    group_chats = await db.get_all_group_chats()
    links = await db.get_all_consult_links()
    events = await db.get_all_events()

    active_pairs: set[tuple[str, str]] = {
        (e["staff_name"], e["cohort"])
        for e in events
        if e.get("week_start") == week_start_str and e.get("type") == "consult"
    }

    for entry in links:
        pair = (entry["staff_name"], entry["cohort"])
        if pair not in active_pairs:
            continue
        group_id = group_chats.get(entry["cohort"])
        if not group_id:
            logger.warning("No group chat configured for cohort %r — skipping link post", entry["cohort"])
            continue
        text = msg.CONSULT_LINK_POST.format(
            staff=_e(entry["staff_name"]),
            cohort=_e(entry["cohort"]),
            link=entry["link"],
        )
        try:
            await bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
            logger.info("Posted consult link for %s / %s to group %d", entry["staff_name"], entry["cohort"], group_id)
        except TelegramError as e:
            logger.error("Failed to post consult link to group %d: %s", group_id, e)


async def sync_schedule(bot: Bot) -> None:
    """Re-fetch Google Sheets and replace events in DB."""
    from sheets_parser import fetch_all_events
    try:
        events = fetch_all_events()
        if not events:
            logger.warning("Sync returned 0 events — retaining existing schedule.")
            return
        await db.replace_events(events)
        await db.log_sync(len(events))
        logger.info("Schedule synced: %d events loaded.", len(events))
    except Exception:
        logger.exception("Schedule sync failed")


async def init_scheduler(bot: Bot) -> None:
    from config import SYNC_INTERVAL_HOURS, STAFF_ID_BY_NAME
    scheduler = get_scheduler()

    for name, dow, h, m, cohort, weekday_label, time_label in _FIXED_SEMINARS:
        scheduler.add_job(
            send_seminar_reminder,
            trigger="cron",
            day_of_week=dow,
            hour=h,
            minute=m,
            timezone=TZ,
            kwargs={
                "bot": bot,
                "chat_id": STAFF_ID_BY_NAME[name],
                "cohort": cohort,
                "weekday": weekday_label,
                "time": time_label,
            },
            id=f"seminar_{name.lower()}_{dow}",
            replace_existing=True,
        )

    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="reminder_check",
        replace_existing=True,
    )
    scheduler.add_job(
        send_completion_checks,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="completion_check",
        replace_existing=True,
    )
    scheduler.add_job(
        check_task_deadlines,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="task_deadlines",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_schedule,
        trigger="interval",
        hours=SYNC_INTERVAL_HOURS,
        kwargs={"bot": bot},
        id="sheet_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        send_weekly_consult_links,
        trigger="cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        timezone=TZ,
        kwargs={"bot": bot},
        id="weekly_consult_links",
        replace_existing=True,
    )
    # Runs every minute; fires at 10:00 local time in each recipient's own zone.
    scheduler.add_job(
        send_weekly_task_reminders,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="weekly_task_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        check_hw_completion_checks,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="hw_completion_checks",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started.")
