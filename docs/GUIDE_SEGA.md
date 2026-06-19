# 👑 Concierge Bot — Owner Guide (Sega)

Full control of the team: schedule, reminders, tasks, TAs, and broadcasts.
Owner-only powers are locked to your account.

---

## 🎛 Main menu

| Button | Command | What it does |
|---|---|---|
| 📅 **My Schedule** | `/upcoming` | Your next upcoming sessions. |
| 📣 **Remind** | `/remind` | Pick a staff member → pick a session → send them a reminder now. |
| 📝 **Assign Task** | `/task` | Assign a custom task with a deadline to any staff member. *(Owner-only)* |
| 📢 **Broadcast** | `/broadcast` | Send one message to **all** registered staff. *(Owner-only)* |
| ⚙️ **Settings** | — | Opens the settings menu below. |

---

## ⚙️ Settings menu

| Button | Command | What it does |
|---|---|---|
| 🔄 **Reload** | `/reload` | Re-sync the schedule from Google Sheets; offers to notify affected staff. |
| 📊 **Sync Status** | `/sync_status` | Last sync time and event count. |
| 🎓 **Assign TA** | `/assignta` | Assign a TA to a cohort → drives that cohort's homework checks. |
| ➕ **Add TA** | `/addta` | Register a new TA (name + Telegram ID). |
| 🔗 **Set Link** | `/setlink` | Save a consult booking link for a cohort. |
| 🌍 **Timezone** | `/timezone` | Change your display timezone. |

---

## ⌨️ Extra commands (type these)

| Command | What it does |
|---|---|
| `/setgroup` | Map a cohort → its group chat ID (so consult links auto-post there). |
| `/listgroups` | List all cohort → group chat mappings. |
| `/clearlinks` | Wipe all saved consult links. |
| `/testlog` | Write a test row to the completions sheet (health check). |

---

## 🗓 What the bot runs on its own

- **Reminders** — 1 h before lectures; 10:00 AM for consults (each in the recipient's zone).
- **Completion checks** — 2 h after every session (Yes/No → reason).
- **Task check-ins** — pre-deadline heads-up + a Yes/No at the deadline.
- **Weekly Saturday 5 PM nudge** — set next week's consult link, or "Done" weekly tasks.
- **Homework checks** — 3 days after each lecture/seminar, sent to the cohort's TA.
- **Auto-skip** — any check-in left unanswered for 24 h is logged as *Skipped*.
- **Schedule sync** — pulls Google Sheets every few hours automatically.

---

## 📊 Where everything is logged (Google Sheets)

| Tab | Contents |
|---|---|
| **Completions Log** + **Dashboard** | Session & weekly-task Yes/No/Skipped, with rollups per staff. |
| **HW Checks Log** + **TA HW Stats** | Homework check results and each TA's completion rate. |
| **Tasks Log** | Every task you assign and its outcome (Assigned → Done / Not done / Skipped). |

---

## 💡 Tips

- **Assign Task** and **Broadcast** are yours alone — no other account can use them.
- After editing the Google Sheet, tap **🔄 Reload** to push changes live and notify affected staff.
- Homework checks only fire for cohorts that have a TA assigned — use **🎓 Assign TA** first.
- Set a cohort's group with `/setgroup` so booking links post automatically when a link is set.
