# tests/conftest.py
import sys
import os
import pytest
import pytest_asyncio
import aiosqlite

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    import database
    database.DB_PATH = db_path
    await database.init_db()
    yield db_path


FIXTURE_LECTURES = [
    {
        "cohort": "April Online",
        "type": "lecture",
        "title": "Lecture #1 (Welcome)",
        "staff_name": "Valera",
        "event_date": "2026-04-25",
        "week_start": None,
        "event_time": "19:30",
        "duration_min": None,
        "notes": None,
    },
    {
        "cohort": "April Online",
        "type": "lecture",
        "title": "Lecture #3 (Narrative)",
        "staff_name": "Tyler",
        "event_date": "2026-05-09",
        "week_start": None,
        "event_time": "19:30",
        "duration_min": None,
        "notes": None,
    },
]

FIXTURE_CONSULTS = [
    {
        "cohort": "February",
        "type": "consult",
        "title": "Consultation",
        "staff_name": "Tyler",
        "event_date": None,
        "week_start": "2026-04-13",
        "event_time": None,
        "duration_min": 45,
        "notes": None,
    },
    {
        "cohort": "April Offline",
        "type": "consult",
        "title": "Consultation",
        "staff_name": "Valera",
        "event_date": None,
        "week_start": "2026-04-20",
        "event_time": None,
        "duration_min": 45,
        "notes": None,
    },
]
