# bot.py
import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import database as db
import messages as msg
from config import ADMIN_CHAT_ID, KNOWN_NAMES, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


def _build_name_keyboard() -> InlineKeyboardMarkup:
    """Build an inline keyboard with one button per known name."""
    buttons = [
        InlineKeyboardButton(name, callback_data=f"register:{name}")
        for name in KNOWN_NAMES
    ]
    # Two buttons per row
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    staff = await db.get_staff(chat_id)
    keyboard = _build_name_keyboard()
    if staff:
        await update.message.reply_text(
            msg.ALREADY_REGISTERED.format(name=staff["display_name"]),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(msg.WELCOME, reply_markup=keyboard)


async def cb_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    name = query.data.split(":", 1)[1]
    await db.upsert_staff(
        chat_id=query.from_user.id,
        username=query.from_user.username,
        display_name=name,
    )
    await query.edit_message_text(msg.REGISTERED.format(name=name))


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    staff = await db.get_staff(chat_id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return

    events = await db.get_upcoming_events_for_staff(staff["display_name"], limit=5)
    if not events:
        await update.message.reply_text(msg.UPCOMING_NONE)
        return

    lines = [msg.UPCOMING_HEADER.format(count=len(events))]
    for e in events:
        event_type = e.get("type")
        event_date_str = e.get("event_date")
        week_start_str = e.get("week_start")

        if event_type == "lecture":
            d = date.fromisoformat(event_date_str)
            lines.append(
                msg.UPCOMING_LECTURE.format(
                    title=e["title"],
                    cohort=e["cohort"],
                    weekday=d.strftime("%A"),
                    date=d.strftime("%B %-d"),
                    time=e["event_time"],
                )
            )
        elif event_date_str:
            # dated consult
            d = date.fromisoformat(event_date_str)
            lines.append(
                msg.UPCOMING_CONSULT_DATE.format(
                    title=e["title"],
                    cohort=e["cohort"],
                    weekday=d.strftime("%A"),
                    date=d.strftime("%B %-d"),
                    duration=e.get("duration_min") or "?",
                )
            )
        else:
            # week consult
            d = date.fromisoformat(week_start_str)
            lines.append(
                msg.UPCOMING_CONSULT_WEEK.format(
                    title=e["title"],
                    cohort=e["cohort"],
                    date=d.strftime("%B %-d"),
                    duration=e.get("duration_min") or "?",
                )
            )

    await update.message.reply_text("".join(lines), parse_mode="Markdown")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    staff = await db.get_staff(chat_id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return
    await db.delete_staff(chat_id)
    await update.message.reply_text(msg.UNREGISTERED)


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    await update.message.reply_text(msg.RELOAD_STARTED)
    try:
        from sheets_parser import fetch_all_events

        events = fetch_all_events()
        if not events:
            await update.message.reply_text(
                "No events returned from sheet — existing schedule retained."
            )
            return
        await db.replace_events(events)
        await db.log_sync(len(events))
        await update.message.reply_text(msg.RELOAD_DONE.format(count=len(events)))
    except Exception as e:
        logger.exception("Reload failed")
        await update.message.reply_text(msg.RELOAD_FAILED.format(error=str(e)))


async def cmd_sync_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    """Build and return the Telegram Application with all handlers registered."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("sync_status", cmd_sync_status))
    app.add_handler(CallbackQueryHandler(cb_register, pattern=r"^register:"))

    return app
