# scheduler.py
import logging
import os
from datetime import datetime, timedelta, date

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.error import TelegramError

import database as db
import messages as msg

logger = logging.getLogger(__name__)
TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))
_scheduler: AsyncIOScheduler | None = None


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
            title=event["title"],
            cohort=event["cohort"],
            weekday=d.strftime("%A"),
            date=d.strftime("%B %-d"),
            time=event["event_time"],
        )
    elif event.get("event_date"):
        d = date.fromisoformat(event["event_date"])
        return msg.REMINDER_CONSULT_DATE.format(
            title=event["title"],
            cohort=event["cohort"],
            weekday=d.strftime("%A"),
            date=d.strftime("%B %-d"),
            duration=event.get("duration_min") or "?",
        )
    else:
        d = date.fromisoformat(event["week_start"])
        return msg.REMINDER_CONSULT_WEEK.format(
            title=event["title"],
            cohort=event["cohort"],
            date=d.strftime("%B %-d"),
            duration=event.get("duration_min") or "?",
        )


async def check_and_send_reminders(bot: Bot) -> None:
    """Check all events for due reminders and send them."""
    now = datetime.now(TZ)
    events = await db.get_all_events()
    staff_list = await db.get_all_staff()

    for event in events:
        reminder_dt = compute_reminder_dt(event)
        if reminder_dt is None:
            continue
        # Fire if within a 2-minute window of the reminder time
        if not (reminder_dt <= now <= reminder_dt + timedelta(minutes=2)):
            continue
        text = format_reminder_message(event)
        for staff in staff_list:
            if staff["display_name"] != event["staff_name"]:
                continue
            if await db.reminder_already_sent(event["id"], staff["chat_id"]):
                continue
            try:
                await bot.send_message(chat_id=staff["chat_id"], text=text)
                await db.log_reminder(event["id"], staff["chat_id"])
                logger.info(
                    "Sent reminder for event %d to chat %d", event["id"], staff["chat_id"]
                )
            except TelegramError as e:
                logger.error("Failed to send reminder to %d: %s", staff["chat_id"], e)


async def sync_schedule(bot: Bot) -> None:
    """Re-fetch Google Sheets and replace events in DB."""
    from parser import fetch_all_events
    try:
        events = fetch_all_events()
        await db.replace_events(events)
        await db.log_sync(len(events))
        logger.info("Schedule synced: %d events loaded.", len(events))
    except Exception as e:
        logger.error("Schedule sync failed: %s", e)


async def init_scheduler(bot: Bot) -> None:
    from config import SYNC_INTERVAL_HOURS
    scheduler = get_scheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        seconds=60,
        kwargs={"bot": bot},
        id="reminder_check",
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
    scheduler.start()
    logger.info("Scheduler started.")
