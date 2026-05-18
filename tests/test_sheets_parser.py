import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sheets_parser import (
    parse_date_string,
    parse_time_string,
    extract_staff_name,
    parse_lectures_sheet,
    parse_consults_grid,
    _extract_duration,
)


def test_parse_date_string_with_day():
    assert parse_date_string("April 25 (Saturday)", 2026) == "2026-04-25"
    assert parse_date_string("May 2 (Saturday)", 2026) == "2026-05-02"
    assert parse_date_string("June 13 (Saturday)", 2026) == "2026-06-13"


def test_parse_date_string_iso():
    assert parse_date_string("2026-04-25", 2026) == "2026-04-25"


def test_parse_date_string_empty_returns_none():
    assert parse_date_string("", 2026) is None
    assert parse_date_string(None, 2026) is None


def test_parse_time_string():
    assert parse_time_string("7:30 PM, GMT+5") == "19:30"
    assert parse_time_string("6:30 PM, GMT+5") == "18:30"
    assert parse_time_string("3:30 PM, GMT+5") == "15:30"


def test_extract_staff_name():
    assert extract_staff_name("Tyler (45 minutes)") == "Tyler"
    assert extract_staff_name("Valera (45 minutes)") == "Valera"
    assert extract_staff_name("Dr. Lyusyena") == "Lyusyena"
    assert extract_staff_name("Rustam (30-45 minutes)") == "Rustam"
    assert extract_staff_name("Alisher / Nigel") == "Alisher"


def test_extract_duration():
    assert _extract_duration("Tyler (45 minutes)") == 45
    assert _extract_duration("Rustam (30-45 minutes)") == 45
    assert _extract_duration("Lyusyena (45-60 mins)") == 60
    assert _extract_duration("no duration here") is None


def test_parse_lectures_sheet_april_online():
    rows = [
        ["April Online AP [2026]", "April 25 (Saturday)", "May 2 (Saturday)", "May 9 (Saturday)"],
        ["Lecturer", "Valera", "Dr. Lyusyena", "Tyler"],
        ["Title", "Lecture #1 (Welcome)", "Lecture #2 (University Fit)", "Lecture #3 (Narrative)"],
        ["Time", "7:30 PM, GMT+5", "7:30 PM, GMT+5", "7:30 PM, GMT+5"],
        ["Seminars (Rustam)", "Wednesday, 7:30-9:00 PM", "", ""],
    ]
    events = parse_lectures_sheet(rows)
    assert len(events) == 3
    lecture1 = events[0]
    assert lecture1["cohort"] == "April Online"
    assert lecture1["staff_name"] == "Valera"
    assert lecture1["event_date"] == "2026-04-25"
    assert lecture1["event_time"] == "19:30"
    assert lecture1["title"] == "Lecture #1 (Welcome)"
    assert lecture1["type"] == "lecture"
    assert lecture1["week_start"] is None

    lecture3 = events[2]
    assert lecture3["staff_name"] == "Tyler"
    assert lecture3["event_date"] == "2026-05-09"


def test_parse_consults_grid():
    rows = [
        ["Weeks", "2026-04-13", "2026-04-20", "2026-04-27"],
        ["Tyler (45 minutes)", "February", "November", "February"],
        ["Valera (45 minutes)", "", "April Offline", ""],
        ["Rustam (30-45 minutes)", "November", "", "April Offline"],
    ]
    events = parse_consults_grid(rows)
    assert len(events) == 6
    tyler_events = [e for e in events if e["staff_name"] == "Tyler"]
    assert len(tyler_events) == 3
    assert all(e["type"] == "consult" for e in tyler_events)
    assert all(e["event_date"] is None for e in tyler_events)
    assert tyler_events[0]["week_start"] == "2026-04-13"
    assert tyler_events[0]["cohort"] == "February"
    assert tyler_events[0]["duration_min"] == 45
    assert tyler_events[1]["week_start"] == "2026-04-20"
    assert tyler_events[1]["cohort"] == "November"
    assert tyler_events[2]["week_start"] == "2026-04-27"
    assert tyler_events[2]["cohort"] == "February"

    valera_events = [e for e in events if e["staff_name"] == "Valera"]
    assert len(valera_events) == 1
    assert valera_events[0]["week_start"] == "2026-04-20"
    assert valera_events[0]["cohort"] == "April Offline"
