# bot.py
import asyncio
import html
import logging
from datetime import date

_e = html.escape

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import database as db
import messages as msg
from config import ADMIN_CHAT_ID, STAFF_IDS, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


async def _handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    name = STAFF_IDS.get(user_id)
    if not name:
        await update.message.reply_text(msg.NOT_ON_ROSTER)
        return
    await db.upsert_staff(
        chat_id=user_id,
        username=update.effective_user.username,
        display_name=name,
    )
    await update.message.reply_text(msg.REGISTERED.format(name=name))


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    staff = await db.get_staff(user_id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return

    events = await db.get_upcoming_events_for_staff(staff["display_name"], limit=5)
    if not events:
        await update.message.reply_text(msg.UPCOMING_NONE)
        return

    lines = [msg.UPCOMING_HEADER.format(count=len(events))]
    for e in events:
        try:
            if e.get("type") == "lecture":
                d = date.fromisoformat(e["event_date"])
                lines.append(
                    msg.UPCOMING_LECTURE.format(
                        title=_e(e["title"]),
                        cohort=_e(e["cohort"]),
                        weekday=d.strftime("%A"),
                        date=d.strftime("%B %-d"),
                        time=e["event_time"] or "TBD",
                    )
                )
            elif e.get("event_date"):
                d = date.fromisoformat(e["event_date"])
                lines.append(
                    msg.UPCOMING_CONSULT_DATE.format(
                        title=_e(e["title"]),
                        cohort=_e(e["cohort"]),
                        weekday=d.strftime("%A"),
                        date=d.strftime("%B %-d"),
                        duration=e.get("duration_min") or "?",
                    )
                )
            else:
                d = date.fromisoformat(e["week_start"])
                lines.append(
                    msg.UPCOMING_CONSULT_WEEK.format(
                        title=_e(e["title"]),
                        cohort=_e(e["cohort"]),
                        date=d.strftime("%B %-d"),
                        duration=e.get("duration_min") or "?",
                    )
                )
        except (ValueError, KeyError) as exc:
            logger.warning("Could not format event %s: %s", e.get("id"), exc)

    await update.message.reply_text("".join(lines), parse_mode="HTML")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    staff = await db.get_staff(user_id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return
    await db.delete_staff(user_id)
    await update.message.reply_text(msg.UNREGISTERED)


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    await update.message.reply_text(msg.RELOAD_STARTED)
    try:
        from sheets_parser import fetch_all_events

        events = await asyncio.to_thread(fetch_all_events)
        if not events:
            await update.message.reply_text(msg.RELOAD_EMPTY)
            return
        await db.replace_events(events)
        await db.log_sync(len(events))
        await update.message.reply_text(msg.RELOAD_DONE.format(count=len(events)))
    except Exception:
        logger.exception("Reload failed")
        await update.message.reply_text(msg.RELOAD_FAILED)


async def cmd_sync_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    last = await db.get_last_sync()
    if last is None:
        await update.message.reply_text(msg.SYNC_STATUS_NONE)
    else:
        await update.message.reply_text(
            msg.SYNC_STATUS.format(
                synced_at=last["synced_at"],
                event_count=last["event_count"],
            )
        )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("sync_status", cmd_sync_status))
    app.add_error_handler(_handle_error)

    return app
