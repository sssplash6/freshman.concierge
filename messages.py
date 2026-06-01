# messages.py

REGISTERED = (
    "✅ You're registered as {name}. You'll receive reminders before your sessions.\n\n"
    "One more thing — share your location so I can set your timezone and send "
    "reminders at the right local time."
)

TZ_PROMPT = (
    "📍 Tap the button below to share your location once. I'll use it only to set "
    "your reminder timezone — your reminders and check-ins will then follow that "
    "zone.\n\nYou can update it any time with /timezone."
)

TZ_SAVED = (
    "✅ Timezone set to <b>{zone}</b> (your local time is now {time}).\n"
    "All your reminders and check-ins will follow this zone."
)

NOT_ON_ROSTER = "You're not on the AP team roster. Contact the admin if this is a mistake."

UNREGISTERED = (
    "✅ You've been unregistered. You will no longer receive reminders.\n"
    "Send /start to register again."
)

NOT_REGISTERED = (
    "You're not registered yet. Send /start to register and receive reminders."
)

ADMIN_ONLY = "This command is for admins only."

UPCOMING_HEADER = "📅 <b>Your next {count} session(s)</b>\n\n"
UPCOMING_NONE = "No upcoming sessions found for your name."

UPCOMING_LECTURE = (
    "🎓 <b>{title}</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 {weekday}, {date} · {time} {tz}</blockquote>\n\n"
)

UPCOMING_CONSULT_DATE = (
    "📋 <b>{title}</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 {weekday}, {date} · {duration} min</blockquote>\n\n"
)

UPCOMING_CONSULT_WEEK = (
    "📋 <b>{title}</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 Week of {date} · {duration} min</blockquote>\n\n"
)

REMINDER_LECTURE = (
    "🔔 <b>Lecture in 1 hour</b>\n"
    "<blockquote>📚 {title}\n"
    "👥 {cohort}\n"
    "📅 {weekday}, {date} · {time} {tz}</blockquote>"
)

REMINDER_CONSULT_DATE = (
    "🔔 <b>Consultation today</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 {weekday}, {date} · {duration} min</blockquote>"
)

REMINDER_CONSULT_WEEK = (
    "🔔 <b>Consultation this week</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 Week of {date} · {duration} min</blockquote>"
)

REMINDER_SEMINAR = (
    "🔔 <b>Seminar in 1 hour</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 {weekday} · {time} GMT+5</blockquote>"
)

RELOAD_STARTED = "🔄 Syncing schedule from Google Sheets..."
RELOAD_DONE_NO_CHANGES = "✅ Sync complete. {count} events loaded. No schedule changes detected."
RELOAD_DONE_CHANGED = "✅ Sync complete. {count} events loaded. Changes detected for {changed} staff member(s) — tap to notify:"
RELOAD_EMPTY = "No events returned from sheet — existing schedule retained."
RELOAD_FAILED = "❌ Sync failed. Check server logs for details."
RELOAD_NOTIFY_SENT = "📣 Notified {count} staff member(s)."
RELOAD_NOTIFY_SKIPPED = "OK, no notification sent."
SCHEDULE_UPDATED = "📅 The schedule has been updated. Use /upcoming to see your latest sessions."

WEEKLY_TASK_REMINDER = (
    "📋 <b>Weekly task</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📝 {title}\n"
    "📅 Week of {date}</blockquote>"
)

COMPLETION_CHECK = (
    "⏱ <b>Session check-in</b>\n"
    "<blockquote>{icon} {title}\n"
    "👥 {cohort}\n"
    "📅 {date}</blockquote>\n\n"
    "Did you complete this session?"
)
COMPLETION_YES_ACK = "✅ Got it, logged as completed. Thanks!"
COMPLETION_NO_PROMPT = "Got it. What happened? Please type a brief reason."
COMPLETION_NO_ACK = "📝 Noted. Thanks for the update."

SETLINK_CHOOSE_COHORT = "🔗 Choose a cohort to set your consultation link for:"
SETLINK_ENTER_LINK = "Send your consultation link for <b>{cohort}</b>:"
SETLINK_SAVED = "✅ Consultation link saved for <b>{cohort}</b>."
SETLINK_NO_COHORTS = "No consultation events found for you in the schedule."
CONSULT_LINK_POST = (
    "🔗 <b>Consultation link</b>\n"
    "<blockquote>👤 {staff}\n"
    "👥 {cohort}\n"
    "🌐 {link}</blockquote>"
)

SETGROUP_CHOOSE_COHORT = "🏘 Choose a cohort to assign a group chat to:"
SETGROUP_ENTER_ID = "Send the group chat ID for <b>{cohort}</b> (a negative number like <code>-1001234567890</code>).\n\nTip: add @userinfobot to the group to get the ID."
SETGROUP_SAVED = "✅ Group chat saved for <b>{cohort}</b>."
SETGROUP_INVALID = "That doesn't look like a valid group chat ID. Send a negative integer (e.g. <code>-1001234567890</code>)."
SETGROUP_NO_COHORTS = "No cohorts found in the schedule. Run a sync first."
SETGROUP_LIST_HEADER = "🏘 <b>Configured group chats</b>\n\n"
SETGROUP_LIST_ROW = "• <b>{cohort}</b>: <code>{chat_id}</code>\n"
SETGROUP_LIST_NONE = "No group chats configured yet."

FALLBACK = "Tap 📅 My Schedule to see your upcoming sessions, or send /start to register."

SYNC_STATUS_NONE = "No sync has been run yet."
SYNC_STATUS = (
    "📊 Last sync: {synced_at}\n"
    "Events loaded: {event_count}"
)
