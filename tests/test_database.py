# tests/test_database.py
import sys
import os
import pytest
import aiosqlite

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
from tests.conftest import FIXTURE_LECTURES, FIXTURE_CONSULTS


@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert {"events", "staff", "reminders_log", "sync_log"} <= tables


@pytest.mark.asyncio
async def test_upsert_and_get_staff(db):
    database.DB_PATH = db
    await database.upsert_staff(chat_id=111, username="tylerhandle", display_name="Tyler")
    staff = await database.get_staff(chat_id=111)
    assert staff["display_name"] == "Tyler"
    assert staff["telegram_username"] == "tylerhandle"


@pytest.mark.asyncio
async def test_delete_staff(db):
    database.DB_PATH = db
    await database.upsert_staff(chat_id=222, username=None, display_name="Nigel")
    await database.delete_staff(chat_id=222)
    assert await database.get_staff(chat_id=222) is None


@pytest.mark.asyncio
async def test_replace_events(db):
    database.DB_PATH = db
    await database.replace_events(FIXTURE_LECTURES)
    events = await database.get_events_for_staff("Valera")
    assert len(events) == 1
    assert events[0]["title"] == "Lecture #1 (Welcome)"


@pytest.mark.asyncio
async def test_replace_events_clears_old(db):
    database.DB_PATH = db
    await database.replace_events(FIXTURE_LECTURES)
    await database.replace_events(FIXTURE_CONSULTS)
    events = await database.get_events_for_staff("Valera")
    assert all(e["type"] == "consult" for e in events)


@pytest.mark.asyncio
async def test_reminder_not_sent_twice(db):
    database.DB_PATH = db
    await database.replace_events(FIXTURE_LECTURES)
    events = await database.get_events_for_staff("Valera")
    event_id = events[0]["id"]
    await database.log_reminder(event_id=event_id, chat_id=111)
    already = await database.reminder_already_sent(event_id=event_id, chat_id=111)
    assert already is True


@pytest.mark.asyncio
async def test_get_upcoming_events(db):
    database.DB_PATH = db
    # Create a fixture with a future date for this test
    future_events = [
        {
            "cohort": "April Online",
            "type": "lecture",
            "title": "Lecture #3 (Narrative)",
            "staff_name": "Tyler",
            "event_date": "2026-06-09",  # Future date
            "week_start": None,
            "event_time": "19:30",
            "duration_min": None,
            "notes": None,
        },
    ]
    await database.replace_events(future_events)
    upcoming = await database.get_upcoming_events_for_staff("Tyler", limit=5)
    assert len(upcoming) == 1
    assert upcoming[0]["title"] == "Lecture #3 (Narrative)"
