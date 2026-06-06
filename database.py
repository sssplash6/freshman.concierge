# database.py
import os
import aiosqlite
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("DB_PATH", "/tmp/concierge_bot.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                cohort       TEXT NOT NULL,
                type         TEXT NOT NULL,
                title        TEXT NOT NULL,
                staff_name   TEXT NOT NULL,
                event_date   TEXT,
                week_start   TEXT,
                event_time   TEXT,
                duration_min INTEGER,
                notes        TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                chat_id           INTEGER PRIMARY KEY,
                telegram_username TEXT,
                display_name      TEXT NOT NULL,
                timezone          TEXT
            )
        """)
        # Lightweight migration: add `timezone` to staff tables created before
        # this column existed. Ignore the error if it's already present.
        try:
            await db.execute("ALTER TABLE staff ADD COLUMN timezone TEXT")
        except aiosqlite.OperationalError:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id   INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                sent_at    TEXT NOT NULL,
                UNIQUE(event_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at   TEXT NOT NULL,
                event_count INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS completions_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT NOT NULL,
                staff_name  TEXT NOT NULL,
                chat_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                cohort      TEXT NOT NULL,
                event_ref   TEXT NOT NULL,
                completed   INTEGER NOT NULL,
                reason      TEXT,
                answered_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS completion_prompts_sent (
                event_id INTEGER NOT NULL,
                chat_id  INTEGER NOT NULL,
                PRIMARY KEY (event_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS consult_links (
                staff_name TEXT NOT NULL,
                cohort     TEXT NOT NULL,
                link       TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (staff_name, cohort)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_completions (
                chat_id    INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                title      TEXT NOT NULL,
                cohort     TEXT NOT NULL,
                PRIMARY KEY (chat_id, week_start, title, cohort)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_reminders_sent (
                chat_id       INTEGER NOT NULL,
                reminded_date TEXT NOT NULL,
                title         TEXT NOT NULL,
                cohort        TEXT NOT NULL,
                PRIMARY KEY (chat_id, reminded_date, title, cohort)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cohort_group_chats (
                cohort  TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_name       TEXT NOT NULL,
                description      TEXT NOT NULL,
                deadline         TEXT NOT NULL,
                assigned_by      TEXT,
                created_at       TEXT NOT NULL,
                predeadline_sent INTEGER NOT NULL DEFAULT 0,
                checkin_sent     INTEGER NOT NULL DEFAULT 0,
                completed        INTEGER,
                reason           TEXT,
                answered_at      TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ta_assignments (
                cohort  TEXT PRIMARY KEY,
                ta_name TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hw_check_prompts_sent (
                event_id INTEGER NOT NULL,
                chat_id  INTEGER NOT NULL,
                PRIMARY KEY (event_id, chat_id)
            )
        """)
        # Stable-key version: survives event table re-syncs that change event IDs.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hw_check_sent_v2 (
                cohort     TEXT NOT NULL,
                event_date TEXT NOT NULL,
                chat_id    INTEGER NOT NULL,
                PRIMARY KEY (cohort, event_date, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hw_completions_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ta_name     TEXT NOT NULL,
                chat_id     INTEGER NOT NULL,
                cohort      TEXT NOT NULL,
                event_ref   TEXT NOT NULL,
                completed   INTEGER NOT NULL,
                answered_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ta_roster (
                telegram_id  INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL
            )
        """)
        # Seed from env var only for cohorts not already in DB
        from config import COHORT_GROUP_CHATS as _env_chats
        for cohort, chat_id in _env_chats.items():
            await db.execute(
                "INSERT OR IGNORE INTO cohort_group_chats (cohort, chat_id) VALUES (?,?)",
                (cohort, chat_id),
            )
        await db.commit()


async def upsert_staff(chat_id: int, username: str | None, display_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO staff (chat_id, telegram_username, display_name)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                telegram_username = excluded.telegram_username,
                display_name = excluded.display_name
            """,
            (chat_id, username, display_name),
        )
        await db.commit()


async def set_staff_timezone(chat_id: int, tz_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE staff SET timezone = ? WHERE chat_id = ?",
            (tz_name, chat_id),
        )
        await db.commit()


async def get_staff(chat_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM staff WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_staff(chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM staff WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def get_all_staff() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM staff")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def replace_events(events: list[dict]) -> set[str]:
    def _fp(e: dict) -> tuple:
        return (
            e.get("cohort") or "",
            e.get("type") or "",
            e.get("title") or "",
            e.get("event_date") or "",
            e.get("week_start") or "",
            e.get("event_time") or "",
            e.get("duration_min") or 0,
        )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT staff_name, cohort, type, title, event_date, week_start, event_time, duration_min FROM events"
        )
        old_by_name: dict[str, set] = {}
        for row in await cursor.fetchall():
            r = dict(row)
            old_by_name.setdefault(r["staff_name"], set()).add(_fp(r))

        new_by_name: dict[str, set] = {}
        for e in events:
            new_by_name.setdefault(e["staff_name"], set()).add(_fp(e))

        affected = {
            n for n in set(old_by_name) | set(new_by_name)
            if old_by_name.get(n) != new_by_name.get(n)
        }

        await db.execute("BEGIN")
        await db.execute("DELETE FROM events")
        await db.executemany(
            """
            INSERT INTO events
                (cohort, type, title, staff_name, event_date, week_start,
                 event_time, duration_min, notes)
            VALUES
                (:cohort, :type, :title, :staff_name, :event_date, :week_start,
                 :event_time, :duration_min, :notes)
            """,
            events,
        )
        await db.commit()

    return affected


async def get_events_for_staff(display_name: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE staff_name = ? ORDER BY event_date, week_start",
            (display_name,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_events() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events ORDER BY event_date, week_start"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_upcoming_events_for_staff(display_name: str, limit: int = 5) -> list[dict]:
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM events
            WHERE staff_name = ?
              AND (
                (event_date IS NOT NULL AND event_date >= ?)
                OR (week_start IS NOT NULL AND week_start >= ?)
              )
            ORDER BY COALESCE(event_date, week_start)
            LIMIT ?
            """,
            (display_name, today, today, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def log_reminder(event_id: int, chat_id: int) -> None:
    sent_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO reminders_log (event_id, chat_id, sent_at) VALUES (?, ?, ?)",
            (event_id, chat_id, sent_at),
        )
        await db.commit()


async def reminder_already_sent(event_id: int, chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM reminders_log WHERE event_id = ? AND chat_id = ?",
            (event_id, chat_id),
        )
        return await cursor.fetchone() is not None


async def log_sync(event_count: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO sync_log (synced_at, event_count) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), event_count),
        )
        await db.commit()


async def completion_prompt_sent(event_id: int, chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM completion_prompts_sent WHERE event_id=? AND chat_id=?",
            (event_id, chat_id),
        )
        return await cursor.fetchone() is not None


async def mark_completion_prompt_sent(event_id: int, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO completion_prompts_sent (event_id, chat_id) VALUES (?,?)",
            (event_id, chat_id),
        )
        await db.commit()


async def log_completion(
    type: str,
    staff_name: str,
    chat_id: int,
    title: str,
    cohort: str,
    event_ref: str,
    completed: bool,
    reason: str | None = None,
) -> None:
    answered_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO completions_log
                (type, staff_name, chat_id, title, cohort, event_ref, completed, reason, answered_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (type, staff_name, chat_id, title, cohort, event_ref, int(completed), reason, answered_at),
        )
        await db.commit()


async def set_consult_link(staff_name: str, cohort: str, link: str) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO consult_links (staff_name, cohort, link, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(staff_name, cohort) DO UPDATE SET
                link = excluded.link,
                updated_at = excluded.updated_at
            """,
            (staff_name, cohort, link, updated_at),
        )
        await db.commit()


async def get_consult_link(staff_name: str, cohort: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT link FROM consult_links WHERE staff_name=? AND cohort=?",
            (staff_name, cohort),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_all_consult_links() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM consult_links")
        return [dict(r) for r in await cursor.fetchall()]


async def get_cohorts_for_staff(staff_name: str) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT cohort FROM events WHERE staff_name=? ORDER BY cohort",
            (staff_name,),
        )
        return [r[0] for r in await cursor.fetchall()]


async def clear_all_consult_links() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM consult_links")
        await db.commit()
        return cursor.rowcount


async def get_event_by_id(event_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def is_weekly_complete(chat_id: int, week_start: str, title: str, cohort: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM weekly_completions WHERE chat_id=? AND week_start=? AND title=? AND cohort=?",
            (chat_id, week_start, title, cohort),
        )
        return await cursor.fetchone() is not None


async def mark_weekly_complete(chat_id: int, week_start: str, title: str, cohort: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO weekly_completions (chat_id, week_start, title, cohort) VALUES (?,?,?,?)",
            (chat_id, week_start, title, cohort),
        )
        await db.commit()


async def weekly_reminder_sent_today(chat_id: int, reminded_date: str, title: str, cohort: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM weekly_reminders_sent WHERE chat_id=? AND reminded_date=? AND title=? AND cohort=?",
            (chat_id, reminded_date, title, cohort),
        )
        return await cursor.fetchone() is not None


async def log_weekly_reminder(chat_id: int, reminded_date: str, title: str, cohort: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO weekly_reminders_sent (chat_id, reminded_date, title, cohort) VALUES (?,?,?,?)",
            (chat_id, reminded_date, title, cohort),
        )
        await db.commit()


async def set_group_chat(cohort: str, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO cohort_group_chats (cohort, chat_id) VALUES (?,?) ON CONFLICT(cohort) DO UPDATE SET chat_id=excluded.chat_id",
            (cohort, chat_id),
        )
        await db.commit()


async def get_all_group_chats() -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT cohort, chat_id FROM cohort_group_chats")
        return {row[0]: row[1] for row in await cursor.fetchall()}


async def get_all_cohorts() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT cohort FROM events ORDER BY cohort")
        return [r[0] for r in await cursor.fetchall()]


async def create_task(staff_name: str, description: str, deadline: str, assigned_by: str) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tasks (staff_name, description, deadline, assigned_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (staff_name, description, deadline, assigned_by, created_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_tasks() -> list[dict]:
    """Tasks not yet answered (completed IS NULL)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE completed IS NULL")
        return [dict(r) for r in await cursor.fetchall()]


async def get_task(task_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def mark_task_flag(task_id: int, field: str) -> None:
    """Set a notification flag (predeadline_sent or checkin_sent) to 1."""
    assert field in ("predeadline_sent", "checkin_sent")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE tasks SET {field} = 1 WHERE id = ?", (task_id,))
        await db.commit()


async def set_task_result(task_id: int, completed: bool, reason: str | None = None) -> None:
    answered_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET completed = ?, reason = ?, answered_at = ? WHERE id = ?",
            (int(completed), reason, answered_at, task_id),
        )
        await db.commit()


async def get_last_sync() -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_ta_assignment(cohort: str, ta_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ta_assignments (cohort, ta_name) VALUES (?,?) "
            "ON CONFLICT(cohort) DO UPDATE SET ta_name=excluded.ta_name",
            (cohort, ta_name),
        )
        await db.commit()


async def get_ta_assignment(cohort: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT ta_name FROM ta_assignments WHERE cohort=?", (cohort,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_all_ta_assignments() -> dict[str, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT cohort, ta_name FROM ta_assignments")
        return {r[0]: r[1] for r in await cursor.fetchall()}


async def hw_check_sent(cohort: str, event_date: str, chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM hw_check_sent_v2 WHERE cohort=? AND event_date=? AND chat_id=?",
            (cohort, event_date, chat_id),
        )
        return await cursor.fetchone() is not None


async def mark_hw_check_sent(cohort: str, event_date: str, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO hw_check_sent_v2 (cohort, event_date, chat_id) VALUES (?,?,?)",
            (cohort, event_date, chat_id),
        )
        await db.commit()


async def log_hw_completion(
    ta_name: str, chat_id: int, cohort: str, event_ref: str, completed: bool
) -> None:
    answered_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO hw_completions_log
                (ta_name, chat_id, cohort, event_ref, completed, answered_at)
            VALUES (?,?,?,?,?,?)
            """,
            (ta_name, chat_id, cohort, event_ref, int(completed), answered_at),
        )
        await db.commit()


async def add_ta_to_roster(telegram_id: int, display_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ta_roster (telegram_id, display_name) VALUES (?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET display_name=excluded.display_name",
            (telegram_id, display_name),
        )
        await db.commit()


async def get_ta_roster() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT telegram_id, display_name FROM ta_roster ORDER BY display_name")
        return [dict(r) for r in await cursor.fetchall()]


async def get_ta_name_from_roster(telegram_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT display_name FROM ta_roster WHERE telegram_id=?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
