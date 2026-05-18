# messages.py

WELCOME = (
    "👋 Welcome to the AP Concierge Bot.\n\n"
    "Please select your name to register and start receiving reminders:"
)

ALREADY_REGISTERED = (
    "You're currently registered as *{name}*.\n"
    "Tap your name below to confirm, or choose a different one:"
)

REGISTERED = "✅ You're registered as {name}. You'll receive reminders before your sessions."

UNREGISTERED = (
    "✅ You've been unregistered. You will no longer receive reminders.\n"
    "Send /start to register again."
)

NOT_REGISTERED = (
    "You're not registered yet. Send /start to register and receive reminders."
)

ADMIN_ONLY = "This command is for admins only."

UPCOMING_HEADER = "📅 Your next {count} session(s):\n\n"
UPCOMING_NONE = "No upcoming sessions found for your name."

UPCOMING_LECTURE = (
    "🎓 *{title}*\n"
    "👥 Cohort: {cohort}\n"
    "📅 {weekday}, {date} · {time} (GMT+5)\n"
)

UPCOMING_CONSULT_DATE = (
    "📋 *{title}*\n"
    "👥 Cohort: {cohort}\n"
    "📅 {weekday}, {date}\n"
    "⏱ {duration} min\n"
)

UPCOMING_CONSULT_WEEK = (
    "📋 *{title}*\n"
    "👥 Cohort: {cohort}\n"
    "📅 Week of {date}\n"
    "⏱ {duration} min\n"
)

REMINDER_LECTURE = (
    "🎓 Reminder: Your lecture starts in 1 hour\n\n"
    "📚 {title}\n"
    "👥 Cohort: {cohort}\n"
    "📅 {weekday}, {date} · {time} (GMT+5)"
)

REMINDER_CONSULT_DATE = (
    "📋 Reminder: Consultation scheduled today\n\n"
    "🗓 {title}\n"
    "👥 Cohort: {cohort}\n"
    "📅 {weekday}, {date}\n"
    "⏱ {duration} min"
)

REMINDER_CONSULT_WEEK = (
    "📋 Reminder: Consultation scheduled this week\n\n"
    "🗓 {title}\n"
    "👥 Cohort: {cohort}\n"
    "📅 Week of {date}\n"
    "⏱ {duration} min"
)

RELOAD_STARTED = "🔄 Syncing schedule from Google Sheets..."
RELOAD_DONE = "✅ Sync complete. {count} events loaded."
RELOAD_FAILED = "❌ Sync failed: {error}"

SYNC_STATUS_NONE = "No sync has been run yet."
SYNC_STATUS = (
    "📊 Last sync: {synced_at}\n"
    "Events loaded: {event_count}"
)
