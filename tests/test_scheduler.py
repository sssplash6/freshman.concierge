import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
import pytz
from scheduler import (
    compute_reminder_dt,
    format_reminder_message,
    staff_tz,
    tz_label,
    event_instant,
    parse_timezone_input,
    tz_pretty,
)

TZ = pytz.timezone("Asia/Tashkent")
ISTANBUL = pytz.timezone("Europe/Istanbul")  # GMT+3


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


# --- Per-user timezone behavior --------------------------------------------

def test_staff_tz_parses_and_falls_back():
    assert staff_tz({"timezone": "Europe/Istanbul"}).zone == "Europe/Istanbul"
    # Missing or invalid values fall back to the team source zone.
    assert staff_tz({}).zone == "Asia/Tashkent"
    assert staff_tz({"timezone": None}).zone == "Asia/Tashkent"
    assert staff_tz({"timezone": "Not/AZone"}).zone == "Asia/Tashkent"


def test_tz_label_formats_offset():
    assert tz_label(TZ.localize(datetime(2026, 5, 9, 12))) == "GMT+5"
    assert tz_label(ISTANBUL.localize(datetime(2026, 5, 9, 12))) == "GMT+3"
    assert tz_label(pytz.UTC.localize(datetime(2026, 5, 9, 12))) == "GMT+0"


LECTURE = {
    "type": "lecture",
    "title": "Lecture #3",
    "cohort": "April Online",
    "event_date": "2026-05-09",
    "event_time": "19:30",
    "duration_min": None,
    "week_start": None,
}


def test_lecture_reminder_instant_is_zone_independent():
    # Absolute firing moment is identical regardless of the recipient's zone.
    assert compute_reminder_dt(LECTURE, TZ) == compute_reminder_dt(LECTURE, ISTANBUL)
    assert compute_reminder_dt(LECTURE, TZ) == event_instant(LECTURE) - timedelta(hours=1)


def test_lecture_display_converts_to_recipient_zone():
    # 19:30 Tashkent == 17:30 Istanbul; only the displayed time/label change.
    tash = format_reminder_message(LECTURE, TZ)
    ist = format_reminder_message(LECTURE, ISTANBUL)
    assert "19:30" in tash and "GMT+5" in tash
    assert "17:30" in ist and "GMT+3" in ist


def test_parse_timezone_input_offsets():
    # All of these mean UTC+5 -> stored as Etc/GMT-5, displayed as GMT+5.
    for text in ("gmt+5", "utc+5", "GMT +5", "+5", "5", "utc+05:00"):
        name = parse_timezone_input(text)
        assert name == "Etc/GMT-5", text
        assert tz_pretty(name) == "GMT+5"
    assert parse_timezone_input("gmt-4") == "Etc/GMT+4"
    assert tz_pretty("Etc/GMT+4") == "GMT-4"
    assert parse_timezone_input("utc") == "UTC"


def test_parse_timezone_input_iana_and_invalid():
    assert parse_timezone_input("Asia/Tashkent") == "Asia/Tashkent"
    assert tz_pretty("Asia/Tashkent") == "Asia/Tashkent (GMT+5)"
    # Unreadable / unsupported inputs return None.
    for bad in ("", "hello", "gmt+5:30", "+15", "Mars/Olympus"):
        assert parse_timezone_input(bad) is None, bad


def test_typed_offset_zone_drives_local_firing():
    # A zone stored via typed entry behaves like any other for 10:00-local nudges.
    event = {"type": "consult", "event_date": "2026-05-14", "event_time": None, "week_start": None}
    tz = staff_tz({"timezone": parse_timezone_input("gmt+3")})
    dt = compute_reminder_dt(event, tz)
    assert dt.hour == 10 and tz_label(dt) == "GMT+3"


def test_consult_nudge_fires_at_10am_local_per_zone():
    event = {"type": "consult", "event_date": "2026-05-14", "event_time": None, "week_start": None}
    tash = compute_reminder_dt(event, TZ)
    ist = compute_reminder_dt(event, ISTANBUL)
    # Both are 10:00 wall-clock in their own zone...
    assert tash.hour == 10 and ist.hour == 10
    # ...but the GMT+3 user's 10:00 is a later absolute instant than GMT+5's.
    assert ist > tash
