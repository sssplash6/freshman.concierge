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
TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))
_scheduler: AsyncIOScheduler | None = None

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


def compute_reminder_dt(event: dict) -> datetime | None:
    """Return the tz-aware datetime (GMT+5) when this event's reminder should fire."""
    if event["type"] == "lecture":
        if not event.get("event_date") or not event.get("event_time"):
            return None
        d = date.fromisoformat(event["event_date"])
        h, m = map(int, event["event_time"].split(":"))
        lecture_dt = TZ.localize(datetime(d.year, d.month, d.day, h, m))
        return lecture_dt - timedelta(hours=1)
    elif event["type"] == "consult":
        if event.get("event_date"):
            d = date.fromisoformat(event["event_date"])
            return TZ.localize(datetime(d.year, d.month, d.day, 10, 0))
        elif event.get("week_start"):
            d = date.fromisoformat(event["week_start"])
            return TZ.localize(datetime(d.year, d.month, d.day, 10, 0))
    return None


def format_reminder_message(event: dict) -> str:
    """Format a reminder message string for the given event."""
    if event["type"] == "lecture":
        d = date.fromisoformat(event["event_date"])
        return msg.REMINDER_LECTURE.format(
            title=_e(event["title"]),
            cohort=_e(event["cohort"]),
            weekday=d.strftime("%A"),
            date=d.strftime("%B %-d"),
            time=event["event_time"] or "TBD",
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
    today = datetime.now(TZ).date()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week
    week_start_str = week_start.isoformat()
    today_str = today.isoformat()

    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        if not event.get("week_start") or event.get("event_date"):
            continue
        if event["week_start"] != week_start_str:
            continue

        for staff in staff_list:
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
    """Check all events for due reminders and send them."""
    now = datetime.now(TZ)
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        reminder_dt = compute_reminder_dt(event)
        if reminder_dt is None:
            continue
        # Fire if past reminder time and within a 30-minute grace window (idempotency prevents duplicates)
        if not (reminder_dt <= now <= reminder_dt + timedelta(minutes=30)):
            continue
        try:
            text = format_reminder_message(event)
        except Exception:
            logger.exception("Failed to format reminder for event %d", event["id"])
            continue
        # Weekly tasks (week_start + no event_date) are handled by send_weekly_task_reminders
        if event.get("week_start") and not event.get("event_date"):
            continue

        for staff in staff_list:
            if staff["display_name"] != event["staff_name"]:
                continue
            if await db.reminder_already_sent(event["id"], staff["chat_id"]):
                continue
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
    now = datetime.now(TZ)
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        if not event.get("event_date") or not event.get("event_time"):
            continue
        d = date.fromisoformat(event["event_date"])
        h, m = map(int, event["event_time"].split(":"))
        check_dt = TZ.localize(datetime(d.year, d.month, d.day, h, m)) + timedelta(hours=2)
        if not (check_dt <= now <= check_dt + timedelta(minutes=30)):
            continue

        icon = "🎓" if event["type"] == "lecture" else "📋"
        text = msg.COMPLETION_CHECK.format(
            icon=icon,
            title=_e(event["title"]),
            cohort=_e(event["cohort"]),
            date=f"{d.strftime('%A, %B %-d')} · {event['event_time']} GMT+5",
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data=f"cc:yes:{event['id']}"),
            InlineKeyboardButton("❌ No",  callback_data=f"cc:no:{event['id']}"),
        ]])

        for staff in staff_list:
            if staff["display_name"] != event["staff_name"]:
                continue
            if await db.completion_prompt_sent(event["id"], staff["chat_id"]):
                continue
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
    from config import COHORT_GROUP_CHATS
    today = datetime.now(TZ).date()
    week_start_str = today.isoformat()

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
        group_id = COHORT_GROUP_CHATS.get(entry["cohort"])
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
    scheduler.add_job(
        send_weekly_task_reminders,
        trigger="cron",
        hour=10,
        minute=0,
        timezone=TZ,
        kwargs={"bot": bot},
        id="weekly_task_reminders",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started.")
