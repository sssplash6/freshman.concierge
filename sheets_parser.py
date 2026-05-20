import logging
import re
from datetime import date

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_NAME_ALIASES: dict[str, str] = {
    "dr. lyusyena": "Lyusyena",
    "lyusyena": "Lyusyena",
    "tyler": "Tyler",
    "valera": "Valera",
    "rustam": "Rustam",
    "nigel": "Nigel",
    "sega": "Sega",
    "sanjar": "Sanjar",
    "alisher": "Alisher",
    "madina": "Madina",
    "komron": "Komron",
}


def extract_staff_name(raw: str) -> str:
    """Extract canonical first name from spreadsheet header like 'Tyler (45 minutes)'."""
    raw = raw.strip()
    first_part = re.split(r"[(/]", raw)[0].strip()
    first_part = re.sub(r"^Dr\.\s*", "", first_part, flags=re.IGNORECASE).strip()
    lookup = first_part.lower()
    return _NAME_ALIASES.get(lookup, first_part.split()[0])


def parse_date_string(value: str | None, year: int = 2026) -> str | None:
    """Parse various date formats -> ISO date string."""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    # ISO date or datetime: "2026-04-25" or "2026-04-25 00:00:00"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if m:
        return m.group(1)
    # M/D/YYYY or MM/DD/YYYY: "5/1/2026"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass
    # "Month Day (Weekday)" or "Month Day, Year": "April 25 (Saturday)", "May 1, 2026"
    m = re.match(r"([A-Za-z]+)\s+(\d+)", value)
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass
    return None


def parse_time_string(value: str | None) -> str | None:
    """Parse '7:30 PM, GMT+5' -> '19:30'."""
    if not value:
        return None
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", value.strip(), re.IGNORECASE)
    if not m:
        return None
    hour, minute, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if period == "PM" and hour != 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _extract_duration(raw: str) -> int | None:
    """Extract minutes from '45 minutes' or '30-45 minutes' -> 45."""
    m = re.search(r"(?:\d+-)?(\d+)\s*min", raw, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _normalize_cohort(raw: str) -> str:
    return " ".join(w.capitalize() for w in raw.strip().split())


def parse_lectures_sheet(rows: list[list[str]]) -> list[dict]:
    """Parse the '2026 Lectures' sheet rows into event dicts."""
    events = []
    current_cohort = None
    current_dates: list[str | None] = []
    current_lecturers: list[str] = []
    current_titles: list[str] = []
    current_times: list[str | None] = []

    COHORT_KEYWORDS = ("AP [2026]", "AP[2026]", "Offline", "Online",
                       "February", "November", "May", "April", "July", "June")

    def _flush():
        nonlocal current_cohort, current_dates, current_lecturers, current_titles, current_times
        if not current_cohort or not current_dates:
            return
        for i, dt in enumerate(current_dates):
            if not dt:
                continue
            lecturer = current_lecturers[i] if i < len(current_lecturers) else ""
            title = current_titles[i] if i < len(current_titles) else ""
            time_str = current_times[i] if i < len(current_times) else None
            if not lecturer or not title:
                continue
            staff = extract_staff_name(lecturer)
            events.append({
                "cohort": current_cohort,
                "type": "lecture",
                "title": title,
                "staff_name": staff,
                "event_date": dt,
                "week_start": None,
                "event_time": parse_time_string(time_str),
                "duration_min": None,
                "notes": None,
            })
        current_cohort = None
        current_dates = []
        current_lecturers = []
        current_titles = []
        current_times = []

    for row in rows:
        if not row or not row[0]:
            continue
        first = str(row[0]).strip()

        is_cohort_header = (
            any(k in first for k in COHORT_KEYWORDS)
            and first not in ("Lecturer", "Title", "Time")
            and not first.startswith("Seminar")
        )

        if is_cohort_header:
            _flush()
            cohort_name = re.sub(r"\s*AP\s*\[?\d*\]?", "", first).strip()
            current_cohort = cohort_name
            current_dates = [parse_date_string(str(c), 2026) for c in row[1:]]
        elif first == "Lecturer":
            current_lecturers = [str(c).strip() for c in row[1:]]
        elif first == "Title":
            current_titles = [str(c).strip() for c in row[1:]]
        elif first == "Time":
            current_times = [str(c).strip() if c else None for c in row[1:]]

    _flush()
    return events


def parse_consults_grid(rows: list[list[str]]) -> list[dict]:
    """Parse the top grid section of '2026 Consults' sheet."""
    events = []
    if not rows:
        return events

    # Find the "Weeks" header row — may not be the first row
    header_idx = None
    for i, row in enumerate(rows):
        if row and str(row[0]).strip() == "Weeks":
            header_idx = i
            break
    if header_idx is None:
        return events

    header = rows[header_idx]
    week_dates = [parse_date_string(str(cell).strip(), 2026) for cell in header[1:]]

    for row in rows[header_idx + 1:]:
        if not row or not row[0]:
            break
        first = str(row[0]).strip()
        if first in ("Research Consults", "EC & Essay Consults", "Post Program",
                     "Consultant", "Notes", "Within the program", "Post program", "Total:"):
            break
        if not any(c in first for c in ("minutes", "mins", "min")):
            break

        staff = extract_staff_name(first)
        duration = _extract_duration(first)

        for i, cohort_raw in enumerate(row[1:]):
            cohort_raw = str(cohort_raw).strip() if cohort_raw else ""
            if not cohort_raw:
                continue
            week_date = week_dates[i] if i < len(week_dates) else None
            if not week_date:
                continue
            cohort = _normalize_cohort(cohort_raw)
            events.append({
                "cohort": cohort,
                "type": "consult",
                "title": "Consultation",
                "staff_name": staff,
                "event_date": None,
                "week_start": week_date,
                "event_time": None,
                "duration_min": duration,
                "notes": None,
            })

    return events


def fetch_all_events() -> list[dict]:
    """Authenticate with Google Sheets and parse all events."""
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEETS_ID

    creds = Credentials.from_service_account_info(
        GOOGLE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES
    )
    gc = gspread.Client(auth=creds)
    sh = gc.open_by_key(GOOGLE_SHEETS_ID)

    events: list[dict] = []

    try:
        ws = sh.worksheet("2026 Lectures")
        rows = ws.get_all_values()
        lecture_events = parse_lectures_sheet(rows)
        events.extend(lecture_events)
        logger.info("Parsed %d lecture events.", len(lecture_events))
    except Exception as e:
        logger.error("Failed to parse 2026 Lectures: %s", e)

    try:
        ws = sh.worksheet("2026 Consults")
        rows = ws.get_all_values()
        consult_events = parse_consults_grid(rows)
        events.extend(consult_events)
        logger.info("Parsed %d consult events.", len(consult_events))
    except Exception as e:
        logger.error("Failed to parse 2026 Consults: %s", e)

    return events
