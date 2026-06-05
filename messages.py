# messages.py

REGISTERED = (
    "✅ You're all set, {name}! You'll receive reminders before your sessions.\n\n"
    "One more step — set your timezone so the timing is right."
)

TZ_PROMPT = (
    "🕔 <b>Set your timezone</b>\n\n"
    "Type your offset or city — e.g. <code>GMT+5</code>, <code>UTC+5</code>, "
    "or <code>Asia/Tashkent</code>."
)

TZ_CONFIRM = (
    "🕔 I read that as <b>{pretty}</b> — your local time is <b>{time}</b>.\n"
    "Is that right?"
)

TZ_INVALID = (
    "🤔 Couldn't read that as a timezone. Try something like <code>GMT+5</code>, "
    "<code>UTC-4</code>, or <code>Europe/Istanbul</code>."
)

TZ_SAVED = (
    "✅ Timezone set to <b>{zone}</b> — local time is <b>{time}</b>.\n"
    "Reminders will follow this zone."
)

NOT_ON_ROSTER = "⛔ You're not on the AP team roster. Contact the admin if this is a mistake."

UNREGISTERED = (
    "✅ You've been unregistered and won't receive any more reminders.\n"
    "Send /start to register again."
)

NOT_REGISTERED = "You're not registered yet. Send /start to get set up."

ADMIN_ONLY = "⛔ This action is admin-only."

UPCOMING_HEADER = "<b>Your next {count} {session_word}</b>\n\n"
UPCOMING_NONE = "You have no upcoming sessions on the schedule."

UPCOMING_LECTURE = (
    "<b>🎓 {title}</b>\n"
    "{cohort} · {weekday}, {date} · {time} {tz}\n\n"
)

UPCOMING_CONSULT_DATE = (
    "<b>📋 Consultation</b>\n"
    "{cohort} · {weekday}, {date} · {duration} min\n\n"
)

UPCOMING_CONSULT_WEEK = (
    "<b>📋 Consultation</b>\n"
    "{cohort} · Week of {date} · {duration} min\n\n"
)

REMINDER_LECTURE = (
    "🔔 <b>Your lecture starts in 1 hour</b>\n"
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
    "🔔 <b>Your seminar starts in 1 hour</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📅 {weekday} · {time} GMT+5</blockquote>"
)

RELOAD_STARTED = "🔄 Syncing schedule from Google Sheets…"
RELOAD_DONE_NO_CHANGES = "✅ Sync complete — {count} events loaded. No schedule changes."
RELOAD_DONE_CHANGED = (
    "✅ Sync complete — {count} events loaded.\n"
    "Schedule changed for {changed} staff member(s). Notify them?"
)
RELOAD_EMPTY = "⚠️ No events returned from the sheet. Existing schedule kept."
RELOAD_FAILED = "❌ Sync failed. Check the server logs for details."
RELOAD_NOTIFY_SENT = "📣 Notified {count} staff member(s)."
RELOAD_NOTIFY_SKIPPED = "OK, no notification sent."
SCHEDULE_UPDATED = "🗓 Your schedule has been updated. Tap 📅 My Schedule to see the latest."

WEEKLY_TASK_REMINDER = (
    "📋 <b>Weekly task reminder</b>\n"
    "<blockquote>👥 {cohort}\n"
    "📝 {title}\n"
    "📅 Week of {date}</blockquote>\n\n"
    "Tap <b>Done</b> below once you've completed this."
)

COMPLETION_CHECK = (
    "✅ <b>Did you complete this session?</b>\n"
    "<blockquote>{icon} {title}\n"
    "👥 {cohort}\n"
    "📅 {date}</blockquote>"
)
COMPLETION_YES_ACK = "✅ Logged as completed. Thanks!"
COMPLETION_NO_PROMPT = "📝 What happened? Send a short reason."
COMPLETION_NO_ACK = "📝 Noted. Thanks for the update."

CANCELLED = "Cancelled."

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
SETGROUP_ENTER_ID = (
    "Send the group chat ID for <b>{cohort}</b> — a negative number like "
    "<code>-1001234567890</code>.\n\n"
    "<i>Tip: add @userinfobot to the group to get the ID.</i>"
)
SETGROUP_SAVED = "✅ Group chat saved for <b>{cohort}</b>."
SETGROUP_INVALID = "That doesn't look right. Send a negative integer, e.g. <code>-1001234567890</code>."
SETGROUP_NO_COHORTS = "No cohorts found in the schedule. Run a sync first."
SETGROUP_LIST_HEADER = "🏘 <b>Configured group chats</b>\n\n"
SETGROUP_LIST_ROW = "• <b>{cohort}</b>: <code>{chat_id}</code>\n"
SETGROUP_LIST_NONE = "No group chats configured yet."

# --- Custom tasks ---------------------------------------------------------
TASK_CHOOSE_PERSON = "👤 Choose who to assign the task to:"
TASK_ENTER_DESC = "📝 What's the task for <b>{name}</b>?"
TASK_CHOOSE_DEADLINE = "⏰ Choose a deadline:"
TASK_ASSIGNED = (
    "✅ Task assigned to <b>{name}</b>.\n"
    "<blockquote>📝 {desc}\n"
    "⏰ Due {deadline}</blockquote>"
)
TASK_NO_TARGET = (
    "⚠️ <b>{name}</b> hasn't started the bot yet, so I can't notify them now. "
    "The task is saved — they'll get the deadline reminder once they do."
)

TASK_NEW = (
    "📋 <b>New task assigned to you</b>\n"
    "<blockquote>📝 {desc}\n"
    "⏰ Due {deadline}\n"
    "👤 Assigned by {by}</blockquote>"
)
TASK_PREDEADLINE = (
    "⚠️ <b>Task due soon</b>\n"
    "<blockquote>📝 {desc}\n"
    "⏰ Due {deadline}</blockquote>"
)
TASK_CHECKIN = (
    "✅ <b>Did you complete this task?</b>\n"
    "<blockquote>📝 {desc}\n"
    "⏰ Due {deadline}</blockquote>"
)

# --- Broadcast ------------------------------------------------------------
BROADCAST_PROMPT = "📢 Type the message you want to send to everyone:"
BROADCAST_PREVIEW = "📢 Preview — this will go to {count} registered user(s):"
BROADCAST_SENT = "✅ Sent to {sent} of {total} user(s)."
BROADCAST_CANCELLED = "OK, broadcast cancelled. Nothing was sent."

FALLBACK = "Tap 📅 My Schedule to see your sessions, or /start to re-register."

SYNC_STATUS_NONE = "No sync has been run yet."
SYNC_STATUS = (
    "📊 <b>Last sync</b>\n"
    "<blockquote>🕒 {synced_at}\n"
    "📆 {event_count} events loaded</blockquote>"
)

# --- TA assignment --------------------------------------------------------
ASSIGN_TA_CHOOSE_COHORT = "🎓 Choose a cohort to assign a TA to:"
ASSIGN_TA_CHOOSE_NAME = "🎓 Assign a TA to <b>{cohort}</b>{current}.\n\nChoose:"
ASSIGN_TA_SAVED = "✅ <b>{ta}</b> is now the TA for <b>{cohort}</b>."

# --- Homework check -------------------------------------------------------
HW_CHECK = (
    "📚 <b>Homework check</b>\n"
    "<blockquote>🎓 {title}\n"
    "👥 {cohort}\n"
    "📅 {date}</blockquote>\n\n"
    "Did you finish checking homework for this session?"
)
HW_CHECK_YES_ACK = "✅ Noted — homework checked!"
HW_CHECK_NO_PROMPT = "📝 Got it — why wasn't homework checked? Send a short reason."
HW_CHECK_NO_ACK = "📋 Noted. Reason logged — don't forget to follow up."
