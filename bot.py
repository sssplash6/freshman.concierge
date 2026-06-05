# bot.py
import asyncio
import html
import logging
from datetime import date, timedelta

_e = html.escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📅 My Schedule"), KeyboardButton("🔗 Set Link")],
        [KeyboardButton("🌍 Timezone")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📅 My Schedule"), KeyboardButton("🔗 Set Link")],
        [KeyboardButton("🔄 Reload"),      KeyboardButton("📊 Sync Status")],
        [KeyboardButton("📣 Remind"),      KeyboardButton("📝 Assign Task")],
        [KeyboardButton("🎓 Assign TA"),   KeyboardButton("📢 Broadcast"),  KeyboardButton("🌍 Timezone")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

import pytz

import database as db
import messages as msg
from config import ADMIN_CHAT_ID, REMIND_IDS, STAFF_IDS, TELEGRAM_BOT_TOKEN
from datetime import datetime as _dt, timezone as _tz
from scheduler import (
    format_reminder_message,
    staff_tz,
    event_instant,
    tz_label,
    format_task_deadline,
    parse_timezone_input,
    tz_pretty,
    SOURCE_TZ,
)
from sheets_parser import append_completion_row, append_hw_check_row


SELECT_PERSON, SELECT_EVENT = range(2)
AWAITING_REASON = 0   # state for completion_conv
SETLINK_COHORT = 0    # states for setlink_conv
SETLINK_URL    = 1
SETGROUP_COHORT = 0   # states for setgroup_conv
SETGROUP_ID     = 1
TASK_PERSON      = 0     # states for task_conv
TASK_DESC        = 1
TASK_DEADLINE    = 2
TASK_CUSTOM_DATE = 3
ASSIGN_TA_COHORT = 0     # states for assign_ta_conv
ASSIGN_TA_NAME   = 1
TZ_TYPE       = 0     # state for timezone_conv
BROADCAST_MSG     = 0  # states for broadcast_conv
BROADCAST_CONFIRM = 1

logger = logging.getLogger(__name__)


async def _handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


def _main_keyboard_for(user_id: int) -> ReplyKeyboardMarkup:
    is_admin = user_id in REMIND_IDS or user_id == ADMIN_CHAT_ID
    return ADMIN_KEYBOARD if is_admin else MAIN_KEYBOARD


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    user_id = update.effective_user.id
    name = STAFF_IDS.get(user_id)
    if not name:
        await update.message.reply_text(msg.NOT_ON_ROSTER)
        return ConversationHandler.END
    await db.upsert_staff(
        chat_id=user_id,
        username=update.effective_user.username,
        display_name=name,
    )
    await update.message.reply_text(
        msg.REGISTERED.format(name=name), reply_markup=_main_keyboard_for(user_id)
    )
    await update.message.reply_text(msg.TZ_PROMPT, parse_mode="HTML")
    return TZ_TYPE


async def cmd_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    staff = await db.get_staff(update.effective_user.id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return ConversationHandler.END
    await update.message.reply_text(msg.TZ_PROMPT, parse_mode="HTML")
    return TZ_TYPE


async def cb_tz_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return TZ_TYPE

    tz_name = parse_timezone_input(update.message.text)
    if not tz_name:
        await update.message.reply_text(msg.TZ_INVALID, parse_mode="HTML")
        return TZ_TYPE

    now_local = _dt.now(pytz.timezone(tz_name))
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data=f"tzset:{tz_name}"),
        InlineKeyboardButton("✖ No",  callback_data="tzcancel"),
    ]])
    await update.message.reply_text(
        msg.TZ_CONFIRM.format(pretty=_e(tz_pretty(tz_name)), time=now_local.strftime("%H:%M")),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return ConversationHandler.END


async def cb_tz_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    tz_name = query.data[len("tzset:"):]
    user_id = query.from_user.id
    await db.set_staff_timezone(user_id, tz_name)
    now_local = _dt.now(pytz.timezone(tz_name))
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        msg.TZ_SAVED.format(zone=_e(tz_pretty(tz_name)), time=now_local.strftime("%H:%M")),
        parse_mode="HTML",
        reply_markup=_main_keyboard_for(user_id),
    )


async def cb_tz_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(msg.TZ_PROMPT, parse_mode="HTML")


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

    tz = staff_tz(staff)
    lines = [msg.UPCOMING_HEADER.format(count=len(events))]
    for e in events:
        try:
            if e.get("type") == "lecture":
                inst = event_instant(e)
                if inst:
                    local = inst.astimezone(tz)
                    weekday, datestr = local.strftime("%A"), local.strftime("%B %-d")
                    timestr, label = local.strftime("%H:%M"), tz_label(local)
                else:
                    d = date.fromisoformat(e["event_date"])
                    weekday, datestr = d.strftime("%A"), d.strftime("%B %-d")
                    timestr = "TBD"
                    label = tz_label(tz.localize(_dt(d.year, d.month, d.day)))
                lines.append(
                    msg.UPCOMING_LECTURE.format(
                        title=_e(e["title"]),
                        cohort=_e(e["cohort"]),
                        weekday=weekday,
                        date=datestr,
                        time=timestr,
                        tz=label,
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


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    await update.message.reply_text(
        "Menu refreshed.",
        reply_markup=_main_keyboard_for(update.effective_user.id),
    )


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


def _event_button_label(event: dict) -> str:
    icon = "🎓" if event["type"] == "lecture" else "📋"
    cohort = event.get("cohort", "")
    if event.get("event_date"):
        d = date.fromisoformat(event["event_date"])
        return f"{icon} {d.strftime('%b %-d')} · {cohort}"
    elif event.get("week_start"):
        d = date.fromisoformat(event["week_start"])
        return f"{icon} Wk {d.strftime('%b %-d')} · {cohort}"
    return f"{icon} {cohort}"


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if update.effective_user.id not in REMIND_IDS:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return ConversationHandler.END

    names = sorted(set(STAFF_IDS.values()))
    keyboard: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(name, callback_data=f"rp:{name}")]
        for name in names
    ]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="rc")])

    await update.message.reply_text(
        "👤 Choose a staff member to remind:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_PERSON


async def cb_remind_person(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    name = query.data[3:]
    context.user_data["remind_name"] = name

    events = await db.get_upcoming_events_for_staff(name, limit=10)
    if not events:
        await query.edit_message_text(f"No upcoming events found for {_e(name)}.")
        return ConversationHandler.END

    context.user_data["remind_events"] = events

    lines = [f"📅 Choose an event to remind <b>{_e(name)}</b> of:\n"]
    for i, e in enumerate(events, 1):
        lines.append(f"{i}. {_event_button_label(e)}")

    number_buttons = [InlineKeyboardButton(str(i), callback_data=f"re:{i}") for i in range(1, len(events) + 1)]
    rows = [number_buttons[i:i+5] for i in range(0, len(number_buttons), 5)]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="rc")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML",
    )
    return SELECT_EVENT


async def cb_remind_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    idx = int(query.data[3:]) - 1
    name = context.user_data.get("remind_name", "")
    events = context.user_data.get("remind_events", [])

    event = events[idx] if 0 <= idx < len(events) else None
    if not event:
        await query.edit_message_text("Event not found.")
        return ConversationHandler.END

    targets = [s for s in await db.get_all_staff() if s["display_name"] == name]
    if not targets:
        await query.edit_message_text(f"⚠️ {_e(name)} hasn't started the bot yet — no chat to send to.")
        return ConversationHandler.END

    text = format_reminder_message(event, staff_tz(targets[0]))
    sent = 0
    for s in targets:
        try:
            await context.bot.send_message(chat_id=s["chat_id"], text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            logger.warning("Failed to send reminder to chat %d", s["chat_id"])

    device_word = "device" if sent == 1 else "devices"
    await query.edit_message_text(f"✅ Reminder sent to {_e(name)} ({sent} {device_word}).")
    return ConversationHandler.END


async def cb_remind_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


async def cmd_setlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    staff = await db.get_staff(update.effective_user.id)
    if not staff:
        await update.message.reply_text(msg.NOT_REGISTERED)
        return ConversationHandler.END

    cohorts = await db.get_cohorts_for_staff(staff["display_name"])
    if not cohorts:
        await update.message.reply_text(msg.SETLINK_NO_COHORTS)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(c, callback_data=f"sl:{c}")] for c in cohorts]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="sl:cancel")])
    await update.message.reply_text(
        msg.SETLINK_CHOOSE_COHORT,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETLINK_COHORT


async def cb_setlink_cohort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    if query.data == "sl:cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    cohort = query.data[3:]
    context.user_data["setlink_cohort"] = cohort
    await query.edit_message_text(
        msg.SETLINK_ENTER_LINK.format(cohort=_e(cohort)),
        parse_mode="HTML",
    )
    return SETLINK_URL


async def cb_setlink_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return SETLINK_URL

    link = update.message.text.strip()
    cohort = context.user_data.pop("setlink_cohort", None)
    if not cohort:
        return ConversationHandler.END

    staff = await db.get_staff(update.effective_user.id)
    if not staff:
        return ConversationHandler.END

    await db.set_consult_link(staff["display_name"], cohort, link)
    await update.message.reply_text(
        msg.SETLINK_SAVED.format(cohort=_e(cohort)),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cmd_setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return ConversationHandler.END

    cohorts = await db.get_all_cohorts()
    if not cohorts:
        await update.message.reply_text(msg.SETGROUP_NO_COHORTS)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(c, callback_data=f"sg:{c}")] for c in cohorts]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="sg:cancel")])
    await update.message.reply_text(
        msg.SETGROUP_CHOOSE_COHORT,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETGROUP_COHORT


async def cb_setgroup_cohort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    if query.data == "sg:cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    cohort = query.data[3:]
    context.user_data["setgroup_cohort"] = cohort
    await query.edit_message_text(
        msg.SETGROUP_ENTER_ID.format(cohort=_e(cohort)),
        parse_mode="HTML",
    )
    return SETGROUP_ID


async def cb_setgroup_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return SETGROUP_ID

    text = update.message.text.strip()
    try:
        chat_id = int(text)
        if chat_id >= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(msg.SETGROUP_INVALID, parse_mode="HTML")
        return SETGROUP_ID

    cohort = context.user_data.pop("setgroup_cohort", None)
    if not cohort:
        return ConversationHandler.END

    await db.set_group_chat(cohort, chat_id)
    await update.message.reply_text(msg.SETGROUP_SAVED.format(cohort=_e(cohort)), parse_mode="HTML")
    return ConversationHandler.END


async def cmd_listgroups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    groups = await db.get_all_group_chats()
    if not groups:
        await update.message.reply_text(msg.SETGROUP_LIST_NONE)
        return

    lines = [msg.SETGROUP_LIST_HEADER]
    for cohort, chat_id in sorted(groups.items()):
        lines.append(msg.SETGROUP_LIST_ROW.format(cohort=_e(cohort), chat_id=chat_id))
    await update.message.reply_text("".join(lines), parse_mode="HTML")


def _deadline_presets() -> list[tuple[str, str, object]]:
    """Ordered (key, button label, aware datetime in team zone) deadline options."""
    now = _dt.now(SOURCE_TZ)

    def at18(d: date):
        return SOURCE_TZ.localize(_dt(d.year, d.month, d.day, 18, 0))

    return [
        ("2h",    "⏰ In 2 hours",     now + timedelta(hours=2)),
        ("today", "🌇 Today 6 PM",     at18(now.date())),
        ("tom",   "🌅 Tomorrow 6 PM",  at18((now + timedelta(days=1)).date())),
        ("d3",    "📅 In 3 days",      at18((now + timedelta(days=3)).date())),
        ("w1",    "🗓 In 1 week",      at18((now + timedelta(days=7)).date())),
    ]


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return ConversationHandler.END

    names = sorted(set(STAFF_IDS.values()))
    keyboard = [[InlineKeyboardButton(name, callback_data=f"tp:{name}")] for name in names]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="tx")])
    await update.message.reply_text(
        msg.TASK_CHOOSE_PERSON, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TASK_PERSON


async def cb_task_person(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    name = query.data[3:]
    context.user_data["task_name"] = name
    await query.edit_message_text(msg.TASK_ENTER_DESC.format(name=_e(name)), parse_mode="HTML")
    return TASK_DESC


async def cb_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return TASK_DESC
    context.user_data["task_desc"] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton(label, callback_data=f"td:{key}")]
                for key, label, _ in _deadline_presets()]
    keyboard.append([InlineKeyboardButton("📆 Custom date", callback_data="td:custom")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="tx")])
    await update.message.reply_text(
        msg.TASK_CHOOSE_DEADLINE, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TASK_DEADLINE


async def cb_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    key = query.data[3:]
    name = context.user_data.pop("task_name", None)
    desc = context.user_data.pop("task_desc", None)
    if not name or not desc:
        await query.edit_message_text("Task setup expired. Please start again.")
        return ConversationHandler.END

    if key == "custom":
        context.user_data["task_name"] = name
        context.user_data["task_desc"] = desc
        await query.edit_message_text(
            "📆 Enter a custom deadline date (e.g. <code>6/15</code>, <code>6/15 3pm</code>, or <code>June 15</code>):",
            parse_mode="HTML",
        )
        return TASK_CUSTOM_DATE

    chosen = next((dt for k, _, dt in _deadline_presets() if k == key), None)
    if chosen is None:
        await query.edit_message_text("Unknown deadline. Please start again.")
        return ConversationHandler.END

    deadline_iso = chosen.astimezone(_tz.utc).isoformat()
    assigned_by = STAFF_IDS.get(query.from_user.id, "Admin")
    task_id = await db.create_task(name, desc, deadline_iso, assigned_by)

    # Notify the recipient(s) immediately.
    targets = [s for s in await db.get_all_staff() if s["display_name"] == name]
    for s in targets:
        try:
            await context.bot.send_message(
                chat_id=s["chat_id"],
                text=msg.TASK_NEW.format(
                    desc=_e(desc),
                    deadline=format_task_deadline(deadline_iso, staff_tz(s)),
                    by=_e(assigned_by),
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Failed to send new-task notice to chat %d", s["chat_id"])

    deadline_label = format_task_deadline(deadline_iso, SOURCE_TZ)
    await query.edit_message_text(
        msg.TASK_ASSIGNED.format(name=_e(name), desc=_e(desc), deadline=deadline_label),
        parse_mode="HTML",
    )
    if not targets:
        await query.message.reply_text(msg.TASK_NO_TARGET.format(name=_e(name)), parse_mode="HTML")
    logger.info("Task %d assigned to %s by %s, due %s", task_id, name, assigned_by, deadline_iso)
    return ConversationHandler.END


async def cb_task_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return TASK_CUSTOM_DATE
    text = update.message.text.strip()
    name = context.user_data.pop("task_name", None)
    desc = context.user_data.pop("task_desc", None)
    if not name or not desc:
        await update.message.reply_text("Task setup expired. Please start again.")
        return ConversationHandler.END

    # Try to parse the typed date using dateutil; default to 6 PM team time.
    try:
        from dateutil import parser as _du_parser
        now = _dt.now(SOURCE_TZ)
        parsed = _du_parser.parse(text, default=_dt(now.year, now.month, now.day, 18, 0))
        # If no time was specified, set to 6 PM.
        if parsed.hour == 0 and parsed.minute == 0 and ":" not in text and "am" not in text.lower() and "pm" not in text.lower():
            parsed = parsed.replace(hour=18, minute=0)
        deadline_dt = SOURCE_TZ.localize(parsed.replace(tzinfo=None))
    except Exception:
        await update.message.reply_text(
            "❌ Couldn't parse that date. Try a format like <code>6/15</code>, <code>6/15 3pm</code>, or <code>June 15</code>.",
            parse_mode="HTML",
        )
        context.user_data["task_name"] = name
        context.user_data["task_desc"] = desc
        return TASK_CUSTOM_DATE

    deadline_iso = deadline_dt.astimezone(_tz.utc).isoformat()
    assigned_by = STAFF_IDS.get(update.effective_user.id, "Admin")
    task_id = await db.create_task(name, desc, deadline_iso, assigned_by)

    targets = [s for s in await db.get_all_staff() if s["display_name"] == name]
    for s in targets:
        try:
            await context.bot.send_message(
                chat_id=s["chat_id"],
                text=msg.TASK_NEW.format(
                    desc=_e(desc),
                    deadline=format_task_deadline(deadline_iso, staff_tz(s)),
                    by=_e(assigned_by),
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Failed to send new-task notice to chat %d", s["chat_id"])

    deadline_label = format_task_deadline(deadline_iso, SOURCE_TZ)
    await update.message.reply_text(
        msg.TASK_ASSIGNED.format(name=_e(name), desc=_e(desc), deadline=deadline_label),
        parse_mode="HTML",
    )
    if not targets:
        await update.message.reply_text(msg.TASK_NO_TARGET.format(name=_e(name)), parse_mode="HTML")
    logger.info("Task %d assigned to %s by %s, due %s (custom)", task_id, name, assigned_by, deadline_iso)
    return ConversationHandler.END


async def cb_task_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Cancelled.")
    context.user_data.pop("task_name", None)
    context.user_data.pop("task_desc", None)
    return ConversationHandler.END


def _task_completion_row(task: dict, completed: bool, reason: str) -> list:
    return [
        _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
        task["staff_name"], "Custom Task",
        task["description"], "—",
        format_task_deadline(task["deadline"], SOURCE_TZ),
        "Yes" if completed else "No", reason,
    ]


async def cb_task_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    task_id = int(query.data[7:])  # strip "tc:yes:"
    task = await db.get_task(task_id)
    if task:
        await db.set_task_result(task_id, True)
        await db.log_completion(
            type="custom_task",
            staff_name=task["staff_name"],
            chat_id=query.from_user.id,
            title=task["description"],
            cohort="—",
            event_ref=task["deadline"],
            completed=True,
        )
        asyncio.create_task(asyncio.to_thread(append_completion_row, _task_completion_row(task, True, "")))

    await query.edit_message_text(msg.COMPLETION_YES_ACK)


async def cb_task_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    task_id = int(query.data[6:])  # strip "tc:no:"
    task = await db.get_task(task_id)
    if not task:
        await query.edit_message_text("Task no longer found.")
        return ConversationHandler.END

    context.user_data["pending_completion"] = {
        "kind": "task",
        "task_id": task_id,
        "staff_name": task["staff_name"],
        "description": task["description"],
        "deadline": task["deadline"],
        "chat_id": query.from_user.id,
    }
    await query.edit_message_text(msg.COMPLETION_NO_PROMPT)
    return AWAITING_REASON


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return ConversationHandler.END
    await update.message.reply_text(msg.BROADCAST_PROMPT)
    return BROADCAST_MSG


async def cb_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return BROADCAST_MSG
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(msg.BROADCAST_PROMPT)
        return BROADCAST_MSG

    context.user_data["broadcast_text"] = text
    count = len(await db.get_all_staff())
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"📢 Send to {count}", callback_data="bcast:send"),
        InlineKeyboardButton("✖ Cancel",            callback_data="bcast:cancel"),
    ]])
    await update.message.reply_text(msg.BROADCAST_PREVIEW.format(count=count))
    await update.message.reply_text(text, reply_markup=keyboard)
    return BROADCAST_CONFIRM


async def cb_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    text = context.user_data.pop("broadcast_text", None)
    if not text:
        await query.edit_message_reply_markup(reply_markup=None)
        return ConversationHandler.END

    staff_list = await db.get_all_staff()
    sent = 0
    for s in staff_list:
        try:
            await context.bot.send_message(chat_id=s["chat_id"], text=text)
            sent += 1
        except Exception:
            logger.warning("Failed to broadcast to chat %d", s["chat_id"])

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(msg.BROADCAST_SENT.format(sent=sent, total=len(staff_list)))
    return ConversationHandler.END


async def cb_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(msg.BROADCAST_CANCELLED)
    context.user_data.pop("broadcast_text", None)
    return ConversationHandler.END


async def handle_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(msg.FALLBACK)


async def _cb_stale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for inline buttons that no longer have an active handler (e.g. after a restart)."""
    query = update.callback_query
    if query:
        await query.answer("Session expired. Please start again.", show_alert=False)


async def cb_reload_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if query.data == "rn:no":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(msg.RELOAD_NOTIFY_SKIPPED)
        return

    staff_list = await db.get_all_staff()
    sent = 0
    for s in staff_list:
        try:
            await context.bot.send_message(
                chat_id=s["chat_id"],
                text=msg.SCHEDULE_UPDATED,
            )
            sent += 1
        except Exception:
            logger.warning("Failed to notify chat %d", s["chat_id"])

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(msg.RELOAD_NOTIFY_SENT.format(count=sent))


async def cb_weekly_complete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer("✅ Marked as complete!")

    event_id = int(query.data[3:])
    event = await db.get_event_by_id(event_id)
    if not event:
        return

    chat_id = query.from_user.id
    await db.mark_weekly_complete(chat_id, event["week_start"], event["title"], event["cohort"])
    await db.log_completion(
        type="weekly_task",
        staff_name=event["staff_name"],
        chat_id=chat_id,
        title=event["title"],
        cohort=event["cohort"],
        event_ref=event["week_start"],
        completed=True,
    )
    row = [
        _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
        event["staff_name"], "Weekly Task",
        event["title"], event["cohort"], event["week_start"], "Yes", "",
    ]
    asyncio.create_task(asyncio.to_thread(append_completion_row, row))
    await query.edit_message_reply_markup(reply_markup=None)


async def cb_completion_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    event_id = int(query.data[8:])  # strip "cc:yes:"
    event = await db.get_event_by_id(event_id)
    if event:
        await db.log_completion(
            type="event",
            staff_name=event["staff_name"],
            chat_id=query.from_user.id,
            title=event["title"],
            cohort=event["cohort"],
            event_ref=event.get("event_date") or event.get("week_start", ""),
            completed=True,
        )
        row = [
            _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
            event["staff_name"], "Event",
            event["title"], event["cohort"],
            event.get("event_date") or event.get("week_start", ""), "Yes", "",
        ]
        asyncio.create_task(asyncio.to_thread(append_completion_row, row))

    await query.edit_message_text(msg.COMPLETION_YES_ACK)


async def cb_completion_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    event_id = int(query.data[7:])  # strip "cc:no:"
    event = await db.get_event_by_id(event_id)
    if not event:
        await query.edit_message_text("Event no longer found.")
        return ConversationHandler.END

    context.user_data["pending_completion"] = {
        "event_id": event_id,
        "staff_name": event["staff_name"],
        "title": event["title"],
        "cohort": event["cohort"],
        "event_ref": event.get("event_date") or event.get("week_start", ""),
        "chat_id": query.from_user.id,
    }
    await query.edit_message_text(msg.COMPLETION_NO_PROMPT)
    return AWAITING_REASON


async def cb_completion_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return AWAITING_REASON

    pending = context.user_data.pop("pending_completion", None)
    if not pending:
        return ConversationHandler.END

    reason = update.message.text.strip()

    if pending.get("kind") == "task":
        await db.set_task_result(pending["task_id"], False, reason)
        await db.log_completion(
            type="custom_task",
            staff_name=pending["staff_name"],
            chat_id=pending["chat_id"],
            title=pending["description"],
            cohort="—",
            event_ref=pending["deadline"],
            completed=False,
            reason=reason,
        )
        task = {
            "staff_name": pending["staff_name"],
            "description": pending["description"],
            "deadline": pending["deadline"],
        }
        asyncio.create_task(asyncio.to_thread(append_completion_row, _task_completion_row(task, False, reason)))
        await update.message.reply_text(msg.COMPLETION_NO_ACK)
        return ConversationHandler.END

    if pending.get("kind") == "hw_check":
        await db.log_hw_completion(
            pending["ta_name"], pending["chat_id"],
            pending["cohort"], str(pending["event_id"]), False,
        )
        row = [
            _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
            pending["ta_name"], pending["cohort"],
            pending["title"], pending["event_date"], "No", reason,
        ]
        asyncio.create_task(asyncio.to_thread(append_hw_check_row, row))
        await update.message.reply_text(msg.HW_CHECK_NO_ACK)
        return ConversationHandler.END

    await db.log_completion(
        type="event",
        staff_name=pending["staff_name"],
        chat_id=pending["chat_id"],
        title=pending["title"],
        cohort=pending["cohort"],
        event_ref=pending["event_ref"],
        completed=False,
        reason=reason,
    )
    row = [
        _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
        pending["staff_name"], "Event",
        pending["title"], pending["cohort"],
        pending["event_ref"], "No", reason,
    ]
    asyncio.create_task(asyncio.to_thread(append_completion_row, row))
    await update.message.reply_text(msg.COMPLETION_NO_ACK)
    return ConversationHandler.END


async def cb_reload_affected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    name = query.data[3:]
    targets = [s for s in await db.get_all_staff() if s["display_name"] == name]
    if not targets:
        await query.message.reply_text(f"⚠️ {_e(name)} hasn't started the bot yet — no chat to send to.")
    else:
        sent = 0
        for s in targets:
            try:
                await context.bot.send_message(chat_id=s["chat_id"], text=msg.SCHEDULE_UPDATED)
                sent += 1
            except Exception:
                logger.warning("Failed to notify chat %d", s["chat_id"])
        device_word = "device" if sent == 1 else "devices"
        await query.message.reply_text(f"✅ Notified {_e(name)} ({sent} {device_word}).")

    remaining = [n for n in context.user_data.get("reload_affected", []) if n != name]
    context.user_data["reload_affected"] = remaining
    if remaining:
        rows = [
            [InlineKeyboardButton(n, callback_data=f"ra:{n}") for n in remaining[i:i + 2]]
            for i in range(0, len(remaining), 2)
        ]
        rows.append([
            InlineKeyboardButton("📣 Notify All", callback_data="rn:yes"),
            InlineKeyboardButton("❌ Skip",        callback_data="rn:no"),
        ])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
    else:
        await query.edit_message_reply_markup(reply_markup=None)


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if update.effective_chat.id != ADMIN_CHAT_ID and update.effective_chat.id not in REMIND_IDS:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    await update.message.reply_text(msg.RELOAD_STARTED)
    try:
        from sheets_parser import fetch_all_events

        events = await asyncio.to_thread(fetch_all_events)
        if not events:
            await update.message.reply_text(msg.RELOAD_EMPTY)
            return
        affected = await db.replace_events(events)
        await db.log_sync(len(events))

        if not affected:
            await update.message.reply_text(msg.RELOAD_DONE_NO_CHANGES.format(count=len(events)))
            return

        sorted_affected = sorted(affected)
        context.user_data["reload_affected"] = sorted_affected
        rows = [
            [InlineKeyboardButton(n, callback_data=f"ra:{n}") for n in sorted_affected[i:i + 2]]
            for i in range(0, len(sorted_affected), 2)
        ]
        rows.append([
            InlineKeyboardButton("📣 Notify All", callback_data="rn:yes"),
            InlineKeyboardButton("❌ Skip",        callback_data="rn:no"),
        ])
        await update.message.reply_text(
            msg.RELOAD_DONE_CHANGED.format(count=len(events), changed=len(affected)),
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except Exception:
        logger.exception("Reload failed")
        await update.message.reply_text(msg.RELOAD_FAILED)


async def cmd_testlog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return

    staff = await db.get_staff(update.effective_user.id)
    name = staff["display_name"] if staff else "TEST"
    row = [
        _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
        name, "Test Log",
        "Spreadsheet logging test", "—", date.today().isoformat(), "Yes", "",
    ]

    await update.message.reply_text("⏳ Writing test row to the completions sheet…")
    try:
        await asyncio.to_thread(append_completion_row, row)
        await update.message.reply_text("✅ Test row written. Check the completions sheet.")
    except Exception as exc:
        logger.exception("Test log write failed")
        await update.message.reply_text(f"❌ Logging failed: {_e(type(exc).__name__)}: {_e(str(exc))}")


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


async def cmd_assign_ta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    if update.effective_user.id not in REMIND_IDS and update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text(msg.ADMIN_ONLY)
        return ConversationHandler.END
    cohorts = await db.get_all_cohorts()
    if not cohorts:
        await update.message.reply_text("No cohorts found in the schedule. Run a sync first.")
        return ConversationHandler.END
    ta_assignments = await db.get_all_ta_assignments()
    keyboard = []
    for cohort in cohorts:
        ta = ta_assignments.get(cohort)
        label = f"{cohort}  →  {ta}" if ta else cohort
        keyboard.append([InlineKeyboardButton(label, callback_data=f"tac:{cohort}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="tacx")])
    await update.message.reply_text(
        msg.ASSIGN_TA_CHOOSE_COHORT, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASSIGN_TA_COHORT


async def cb_assign_ta_cohort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    cohort = query.data[4:]  # strip "tac:"
    context.user_data["assign_ta_cohort"] = cohort
    current = await db.get_ta_assignment(cohort)
    current_txt = f" (currently: {_e(current)})" if current else ""
    from config import TA_NAMES
    keyboard = [[InlineKeyboardButton(name, callback_data=f"tan:{name}")] for name in TA_NAMES]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="tacx")])
    await query.edit_message_text(
        msg.ASSIGN_TA_CHOOSE_NAME.format(cohort=_e(cohort), current=current_txt),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ASSIGN_TA_NAME


async def cb_assign_ta_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    ta_name = query.data[4:]  # strip "tan:"
    cohort = context.user_data.pop("assign_ta_cohort", None)
    if not cohort:
        await query.edit_message_text("Assignment expired. Please start again.")
        return ConversationHandler.END
    await db.set_ta_assignment(cohort, ta_name)
    await query.edit_message_text(
        msg.ASSIGN_TA_SAVED.format(ta=_e(ta_name), cohort=_e(cohort)),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cb_assign_ta_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Cancelled.")
    context.user_data.pop("assign_ta_cohort", None)
    return ConversationHandler.END


async def cb_hw_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    event_id = int(query.data[7:])  # strip "hw:yes:"
    event = await db.get_event_by_id(event_id)
    if event:
        staff = await db.get_staff(query.from_user.id)
        ta_name = staff["display_name"] if staff else "unknown"
        await db.log_hw_completion(ta_name, query.from_user.id, event["cohort"], str(event_id), True)
        row = [
            _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M UTC"),
            ta_name, event["cohort"], event["title"],
            event.get("event_date", ""), "Yes", "",
        ]
        asyncio.create_task(asyncio.to_thread(append_hw_check_row, row))
    await query.edit_message_text(msg.HW_CHECK_YES_ACK)


async def cb_hw_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    event_id = int(query.data[6:])  # strip "hw:no:"
    event = await db.get_event_by_id(event_id)
    if not event:
        await query.edit_message_text("HW check no longer found.")
        return ConversationHandler.END
    staff = await db.get_staff(query.from_user.id)
    ta_name = staff["display_name"] if staff else "unknown"
    context.user_data["pending_completion"] = {
        "kind": "hw_check",
        "event_id": event_id,
        "ta_name": ta_name,
        "chat_id": query.from_user.id,
        "cohort": event["cohort"],
        "title": event["title"],
        "event_date": event.get("event_date", ""),
    }
    await query.edit_message_text(msg.HW_CHECK_NO_PROMPT)
    return AWAITING_REASON


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    setlink_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setlink", cmd_setlink),
            MessageHandler(filters.Text(["🔗 Set Link"]), cmd_setlink),
        ],
        states={
            SETLINK_COHORT: [CallbackQueryHandler(cb_setlink_cohort, pattern=r"^sl:")],
            SETLINK_URL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_setlink_url)],
        },
        fallbacks=[CallbackQueryHandler(cb_setlink_cohort, pattern=r"^sl:cancel$")],
        per_chat=True,
        per_message=False,
    )

    completion_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_completion_no, pattern=r"^cc:no:"),
            CallbackQueryHandler(cb_task_no,       pattern=r"^tc:no:"),
            CallbackQueryHandler(cb_hw_no,         pattern=r"^hw:no:"),
        ],
        states={
            AWAITING_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_completion_reason)],
        },
        fallbacks=[],
        allow_reentry=True,
        per_chat=True,
        per_message=False,
    )

    task_conv = ConversationHandler(
        entry_points=[
            CommandHandler("task", cmd_task),
            MessageHandler(filters.Text(["📝 Assign Task"]), cmd_task),
        ],
        states={
            TASK_PERSON:      [CallbackQueryHandler(cb_task_person, pattern=r"^tp:")],
            TASK_DESC:        [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_task_desc)],
            TASK_DEADLINE:    [CallbackQueryHandler(cb_task_deadline, pattern=r"^td:")],
            TASK_CUSTOM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_task_custom_date)],
        },
        fallbacks=[CallbackQueryHandler(cb_task_cancel, pattern=r"^tx$")],
        per_chat=True,
        per_message=False,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", cmd_broadcast),
            MessageHandler(filters.Text(["📢 Broadcast"]), cmd_broadcast),
        ],
        states={
            BROADCAST_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_broadcast_text)],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(cb_broadcast_send,   pattern=r"^bcast:send$"),
                CallbackQueryHandler(cb_broadcast_cancel, pattern=r"^bcast:cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cb_broadcast_cancel, pattern=r"^bcast:cancel$")],
        per_chat=True,
        per_message=False,
    )

    timezone_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("timezone", cmd_timezone),
            MessageHandler(filters.Text(["🌍 Timezone"]), cmd_timezone),
        ],
        states={
            TZ_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_tz_text),
            ],
        },
        fallbacks=[],
        per_chat=True,
        per_message=False,
    )

    remind_conv = ConversationHandler(
        entry_points=[
            CommandHandler("remind", cmd_remind),
            MessageHandler(filters.Text(["📣 Remind"]), cmd_remind),
        ],
        states={
            SELECT_PERSON: [CallbackQueryHandler(cb_remind_person, pattern=r"^rp:")],
            SELECT_EVENT:  [CallbackQueryHandler(cb_remind_event,  pattern=r"^re:")],
        },
        fallbacks=[CallbackQueryHandler(cb_remind_cancel, pattern=r"^rc$")],
        per_message=False,
    )

    setgroup_conv = ConversationHandler(
        entry_points=[CommandHandler("setgroup", cmd_setgroup)],
        states={
            SETGROUP_COHORT: [CallbackQueryHandler(cb_setgroup_cohort, pattern=r"^sg:")],
            SETGROUP_ID:     [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_setgroup_id)],
        },
        fallbacks=[CallbackQueryHandler(cb_setgroup_cohort, pattern=r"^sg:cancel$")],
        per_chat=True,
        per_message=False,
    )

    assign_ta_conv = ConversationHandler(
        entry_points=[
            CommandHandler("assignta", cmd_assign_ta),
            MessageHandler(filters.Text(["🎓 Assign TA"]), cmd_assign_ta),
        ],
        states={
            ASSIGN_TA_COHORT: [CallbackQueryHandler(cb_assign_ta_cohort, pattern=r"^tac:")],
            ASSIGN_TA_NAME:   [CallbackQueryHandler(cb_assign_ta_name,   pattern=r"^tan:")],
        },
        fallbacks=[CallbackQueryHandler(cb_assign_ta_cancel, pattern=r"^tacx$")],
        per_chat=True,
        per_message=False,
    )

    app.add_handler(setlink_conv)
    app.add_handler(setgroup_conv)
    app.add_handler(completion_conv)
    app.add_handler(remind_conv)
    app.add_handler(task_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(timezone_conv)
    app.add_handler(assign_ta_conv)
    app.add_handler(CallbackQueryHandler(cb_completion_yes, pattern=r"^cc:yes:"))
    app.add_handler(CallbackQueryHandler(cb_task_yes, pattern=r"^tc:yes:"))
    app.add_handler(CallbackQueryHandler(cb_hw_yes, pattern=r"^hw:yes:"))
    app.add_handler(CallbackQueryHandler(cb_tz_confirm, pattern=r"^tzset:"))
    app.add_handler(CallbackQueryHandler(cb_tz_cancel, pattern=r"^tzcancel$"))
    app.add_handler(CallbackQueryHandler(cb_weekly_complete, pattern=r"^wc:"))
    app.add_handler(CallbackQueryHandler(cb_reload_affected, pattern=r"^ra:"))
    app.add_handler(CallbackQueryHandler(cb_reload_notify, pattern=r"^rn:"))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(MessageHandler(filters.Text(["📅 My Schedule"]), cmd_upcoming))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(MessageHandler(filters.Text(["🔄 Reload"]), cmd_reload))
    app.add_handler(CommandHandler("sync_status", cmd_sync_status))
    app.add_handler(MessageHandler(filters.Text(["📊 Sync Status"]), cmd_sync_status))
    app.add_handler(CommandHandler("listgroups", cmd_listgroups))
    app.add_handler(CommandHandler("testlog", cmd_testlog))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fallback))
    app.add_handler(CallbackQueryHandler(_cb_stale))
    app.add_error_handler(_handle_error)

    return app
