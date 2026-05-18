import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
import pytz
from scheduler import compute_reminder_dt, format_reminder_message

TZ = pytz.timezone("Asia/Tashkent")


def test_lecture_reminder_is_one_hour_before():
    event = {
        "type": "lecture",
        "event_date": "2026-05-09",
        "event_time": "19:30",
        "week_start": None,
    }
    dt = compute_reminder_dt(event)
    expected = TZ.localize(datetime(2026, 5, 9, 18, 30))
    assert dt == expected


def test_consult_with_date_reminder_is_10am():
    event = {
        "type": "consult",
        "event_date": "2026-05-14",
        "event_time": None,
        "week_start": None,
    }
    dt = compute_reminder_dt(event)
    expected = TZ.localize(datetime(2026, 5, 14, 10, 0))
    assert dt == expected


def test_consult_with_week_reminder_is_monday_10am():
    event = {
        "type": "consult",
        "event_date": None,
        "event_time": None,
        "week_start": "2026-06-08",
    }
    dt = compute_reminder_dt(event)
    expected = TZ.localize(datetime(2026, 6, 8, 10, 0))
    assert dt == expected


def test_reminder_returns_none_for_missing_dates():
    event = {"type": "consult", "event_date": None, "event_time": None, "week_start": None}
    assert compute_reminder_dt(event) is None


def test_format_reminder_lecture():
    event = {
        "type": "lecture",
        "title": "Lecture #3 (Narrative)",
        "cohort": "April Online",
        "event_date": "2026-05-09",
        "event_time": "19:30",
        "duration_min": None,
        "week_start": None,
    }
    msg = format_reminder_message(event)
    assert "1 hour" in msg
    assert "Lecture #3 (Narrative)" in msg
    assert "April Online" in msg
    assert "19:30" in msg


def test_format_reminder_consult_date():
    event = {
        "type": "consult",
        "title": "EC Development",
        "cohort": "November",
        "event_date": "2026-05-14",
        "event_time": None,
        "duration_min": 45,
        "week_start": None,
    }
    msg = format_reminder_message(event)
    assert "today" in msg
    assert "EC Development" in msg
    assert "45 min" in msg


def test_format_reminder_consult_week():
    event = {
        "type": "consult",
        "title": "Consultation",
        "cohort": "February",
        "event_date": None,
        "event_time": None,
        "duration_min": 30,
        "week_start": "2026-06-08",
    }
    msg = format_reminder_message(event)
    assert "this week" in msg
    assert "30 min" in msg
