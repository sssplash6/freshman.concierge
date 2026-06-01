# scheduler.py
import html
import logging
import os
from datetime import datetime, timedelta, date
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
    raise ValueError(f"Unknown event type: {event['type']!r}")


def format_weekly_task_reminder(event: dict) -> str:
    d = date.fromisoformat(event["week_start"])
    return msg.WEEKLY_TASK_REMINDER.format(
        cohort=_e(event["cohort"]),
        title=_e(event["title"]),
        date=d.strftime("%B %-d"),
    )


async def send_weekly_task_reminders(bot: Bot) -> None:
    """Daily 10:00 nudge (in each recipient's own zone) for pending weekly tasks.

    Runs on a 60-second interval; the per-staff local 10:00–10:30 window plus the
    once-per-day idempotency key keep it to a single send per task per day.
    """
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for staff in staff_list:
        now_local = datetime.now(staff_tz(staff))
        # Only fire during the recipient's local 10:00–10:30 window.
        if not (now_local.hour == 10 and now_local.minute < 30):
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
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started.")
