# messages.py

REGISTERED = "✅ You're registered as {name}. You'll receive reminders before your sessions."

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
    "📅 {weekday}, {date} · {time} GMT+5</blockquote>\n\n"
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
    "📅 {weekday}, {date} · {time} GMT+5</blockquote>"
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

FALLBACK = "Tap 📅 My Schedule to see your upcoming sessions, or send /start to register."

SYNC_STATUS_NONE = "No sync has been run yet."
SYNC_STATUS = (
    "📊 Last sync: {synced_at}\n"
    "Events loaded: {event_count}"
)
