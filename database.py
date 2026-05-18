# database.py
import os
import aiosqlite
from datetime import date, datetime, timezone

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
                display_name      TEXT NOT NULL
            )
        """)
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


async def replace_events(events: list[dict]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
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
    today = date.today().isoformat()
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


async def get_last_sync() -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
