# Concierge Bot — Full Functionality Reference

## Overview

Telegram bot for the AP team. It reads the schedule from Google Sheets and automatically reminds staff (coaches, instructors) about their upcoming lectures, consultations, and weekly tasks. It also collects completion confirmations and logs them back to Google Sheets for analytics.

All times are GMT+5 (Asia/Tashkent).

---

## Registration

### `/start`
Staff member registers with the bot. The bot checks the sender's Telegram ID against `STAFF_IDS` in `config.py`. If the ID is on the roster, the user is saved to the DB and receives a persistent keyboard. Admins get an extended keyboard with additional buttons. Unknown IDs are rejected.

### `/cancel`
Unregisters the user — removes them from the DB and stops all future reminders. They can re-register with `/start`.

---

## Staff Commands

### `📅 My Schedule` / `/upcoming`
Shows the next 5 upcoming sessions for the logged-in staff member. Displays event type (lecture or consultation), cohort, date, time, and duration. For week-based consultations (no fixed date), shows the week start date.

### `🔗 Set Link` / `/setlink`
Lets a staff member save their personal consultation link for a specific cohort. Flow:
1. Bot shows cohort buttons (only cohorts where the user has consultation events).
2. User picks a cohort.
3. User sends their link (URL).
4. Link is saved to the DB and used in the Monday group chat post.

---

## Automated Reminders (Scheduler)

All scheduled jobs run in the background via APScheduler.

### Lecture reminders
Fires **1 hour before** a lecture's scheduled time. Sent individually to the staff member's private chat. Deduplication — each reminder is only sent once per event per user (logged to `reminders_log`).

### Consultation reminders (date-specific)
Fires at **10:00 AM on the day** of the consultation. Sent to the staff member's private chat.

### Consultation reminders (week-based)
Fires at **10:00 AM on Monday** of the consultation week. Sent to the staff member's private chat.

### Weekly task reminders
Fires daily at **10:00 AM** for any task that has a week assignment but no specific date (e.g. "record feedback video this week"). Sent every day until the staff member marks it done. Once marked complete, reminders stop for that week.

- Staff tap **✅ Done** on the reminder message to mark it complete.
- Completion is logged to `completions_log` and to Google Sheets.

### Completion check-ins
Fires **2 hours after** any timed event (lectures and date-specific consultations). Asks the staff member: "Did you complete this session?"

- **Yes** → logged as completed in DB and Google Sheets.
- **No** → bot asks for a brief reason, then logs it as not completed with the reason.

Each check-in is only sent once per event per user.

### Fixed seminar reminders
Hard-coded weekly reminders for seminars with a fixed recurring schedule (no Google Sheets entry needed):

| Staff | Cohort | Day | Time (GMT+5) |
|-------|--------|-----|--------------|
| Gulrukh | April Offline | Wednesday | 6:30 PM |
| Rustam | April Online | Wednesday | 7:30 PM |
| Gulrukh | May Offline | Saturday | 3:00 PM |
| Rustam | May Online | Thursday | 7:30 PM |

### Monday consultation link post
Every **Monday at 9:00 AM**, the bot posts each staff member's saved consultation link to the relevant cohort group chat. Only posts for staff who have an active consultation scheduled for that week and have saved a link.

### Auto-sync
Automatically re-fetches the Google Sheets schedule every N hours (configured via `SYNC_INTERVAL_HOURS` env var, default 6). Replaces all events in the DB.

---

## Admin Commands

Admin access is granted to users whose Telegram ID is in `REMIND_IDS` (the "Sega" entries in `STAFF_IDS`) or matches `ADMIN_CHAT_ID` (env var).

### `🔄 Reload` / `/reload`
Manually triggers a Google Sheets sync. After loading:
- If nothing changed: confirms with event count.
- If changes detected: shows buttons for each affected staff member. Admin can tap each name to notify them individually, or use **📣 Notify All** to message everyone at once, or **❌ Skip** to do nothing.

Notification message tells the staff member their schedule was updated and to check `/upcoming`.

### `📊 Sync Status` / `/sync_status`
Shows the timestamp and event count of the last successful sync.

### `📣 Remind` / `/remind`
Manually sends a reminder to any staff member for any of their upcoming events. Flow:
1. Pick a staff member from a button list.
2. Pick an event from a numbered list.
3. Bot sends the reminder to that person's chat immediately.

### `/setgroup`
Assigns a Telegram group chat ID to a cohort. Flow:
1. Bot shows all cohorts in the current schedule as buttons.
2. Admin picks a cohort.
3. Admin sends the group chat ID (a negative integer, e.g. `-1001234567890`).
4. Saved to DB — used by the Monday consultation link post.

Group chat IDs set here override anything from the `COHORT_GROUP_CHATS` env var. The env var is only used to seed initial values on first run.

### `/listgroups`
Shows all currently configured cohort → group chat ID mappings.

---

## Data Storage

All data is stored in SQLite (path configured via `DB_PATH` env var, default `/tmp/concierge_bot.db`).

| Table | Purpose |
|-------|---------|
| `events` | Full schedule synced from Google Sheets |
| `staff` | Registered users (chat ID, username, display name) |
| `reminders_log` | Which reminders have been sent (deduplication) |
| `completion_prompts_sent` | Which completion check-ins have been sent |
| `completions_log` | All completion responses (yes/no + reason) |
| `weekly_completions` | Which weekly tasks are marked done per user per week |
| `weekly_reminders_sent` | Daily deduplication for weekly task reminders |
| `consult_links` | Staff consultation links per cohort |
| `cohort_group_chats` | Cohort → Telegram group chat ID mapping |
| `sync_log` | History of sheet syncs (timestamp + event count) |

---

## Google Sheets Integration

- Schedule is read from a Google Sheet via a service account.
- Parsed by `sheets_parser.py` — extracts lectures, consultations, and weekly tasks per staff member and cohort.
- Completion data is appended to an analytics tab in the same sheet via `append_completion_row`.

---

## Configuration (Environment Variables)

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `ADMIN_CHAT_ID` | Yes | Telegram ID of the primary admin |
| `GOOGLE_SHEETS_ID` | Yes | ID of the Google Sheet |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Yes | Full JSON of the service account key |
| `DB_PATH` | No | SQLite file path (default: `/tmp/concierge_bot.db`) |
| `SYNC_INTERVAL_HOURS` | No | Auto-sync frequency in hours (default: `6`) |
| `COHORT_GROUP_CHATS` | No | JSON map of cohort name → group chat ID for initial seeding |
| `TIMEZONE` | No | Timezone for scheduler (default: `Asia/Tashkent`) |
