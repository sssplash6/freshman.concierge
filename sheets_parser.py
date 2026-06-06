import logging
import re
from datetime import date

_re = re

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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
    "gulrukh": "Gulrukh",
    "husanboy": "Husanboy",
    "madina": "Madina",
    "bekah": "Bekah",
    "firdas": "Firdas",
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
    # M/D/YYYY or MM/DD/YYYY, optionally with trailing text: "5/1/2026", "6/2/2026 (Test)"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", value)
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


_COMPLETIONS_HEADERS = ["Timestamp", "Staff Name", "Type", "Title", "Cohort", "Date", "Completed", "Reason"]
_LOG = "Completions Log"
_DASH = "Dashboard"

_HW_LOG = "HW Checks Log"
_HW_HEADERS = ["Timestamp", "TA Name", "Cohort", "Event Title", "Event Date", "Completed", "Reason"]


def _rgb(r: float, g: float, b: float) -> dict:
    return {"red": r, "green": g, "blue": b}


def _setup_log_sheet(ws) -> None:
    sid = ws.id
    sh = ws.spreadsheet
    # Column widths: Timestamp, Staff, Type, Title, Cohort, Date, Completed, Reason
    col_widths = [175, 110, 110, 220, 130, 110, 100, 290]
    requests = [
        # Header row: dark navy bg, white bold text, centered, 36px tall
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 8},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _rgb(0.129, 0.196, 0.341),
                    "textFormat": {"bold": True, "fontSize": 11,
                                   "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        },
        # Freeze header row
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Header row height
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 36},
                "fields": "pixelSize",
            }
        },
    ]
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    sh.batch_update({"requests": requests})


def _format_log_row(ws, row_idx: int, completed: bool) -> None:
    sid = ws.id
    i = row_idx - 1  # 0-based
    row_bg = _rgb(0.851, 0.957, 0.851) if completed else _rgb(0.988, 0.894, 0.882)
    badge_bg = _rgb(0.204, 0.659, 0.325) if completed else _rgb(0.820, 0.165, 0.118)
    ws.spreadsheet.batch_update({"requests": [
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1,
                          "startColumnIndex": 0, "endColumnIndex": 8},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": row_bg,
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,verticalAlignment)",
            }
        },
        # "Yes" / "No" badge — column G (index 6)
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1,
                          "startColumnIndex": 6, "endColumnIndex": 7},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": badge_bg,
                    "textFormat": {"bold": True,
                                   "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
    ]})


def _setup_dashboard(sh) -> None:
    import gspread
    from config import STAFF_IDS
    staff_names = sorted(set(STAFF_IDS.values()))
    log = f"'{_LOG}'"

    try:
        dash = sh.worksheet(_DASH)
    except gspread.exceptions.WorksheetNotFound:
        dash = sh.add_worksheet(_DASH, rows=200, cols=6)

    # --- Build cell grid ---
    data: list[list] = [
        ["📊 Completions Dashboard", "", "", "", "", ""],
        [""],
        ["", "Events ✅", "Events ❌", "Weekly Tasks ✅", "Completion Rate", ""],
        [
            "TOTALS",
            f"=COUNTIFS({log}!G:G,\"Yes\",{log}!C:C,\"Event\")",
            f"=COUNTIFS({log}!G:G,\"No\",{log}!C:C,\"Event\")",
            f"=COUNTIFS({log}!G:G,\"Yes\",{log}!C:C,\"Weekly Task\")",
            f"=IFERROR(TEXT(B4/(B4+C4),\"0%\"),\"—\")",
            "",
        ],
        [""],
        ["Staff Breakdown", "Events ✅", "Events ❌", "Weekly Tasks ✅", "Rate", ""],
    ]
    for name in staff_names:
        row_n = len(data) + 1
        data.append([
            name,
            f"=COUNTIFS({log}!B:B,\"{name}\",{log}!G:G,\"Yes\",{log}!C:C,\"Event\")",
            f"=COUNTIFS({log}!B:B,\"{name}\",{log}!G:G,\"No\",{log}!C:C,\"Event\")",
            f"=COUNTIFS({log}!B:B,\"{name}\",{log}!G:G,\"Yes\",{log}!C:C,\"Weekly Task\")",
            f"=IFERROR(TEXT(B{row_n}/(B{row_n}+C{row_n}),\"0%\"),\"—\")",
            "",
        ])

    recent_start = len(data) + 2
    data.append([""])
    data.append(["Recent Non-Completions", "", "", "", "", ""])
    data.append([
        f"=IFERROR(QUERY({log}!A:H,\"SELECT A,B,D,E,F,H WHERE G='No' ORDER BY A DESC LIMIT 15 LABEL A 'When',B 'Staff',D 'Title',E 'Cohort',F 'Date',H 'Reason'\",1),\"No non-completions yet\")",
        "", "", "", "", "",
    ])

    dash.update("A1", data, value_input_option="USER_ENTERED")

    sid = dash.id
    requests = [
        # Title: big, bold, dark
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _rgb(0.129, 0.196, 0.341),
                    "textFormat": {"bold": True, "fontSize": 16,
                                   "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        },
        # Title row height
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 48},
                "fields": "pixelSize",
            }
        },
        # Section header rows (row 3 = index 2, row 6 = index 5, recent_start-1)
        *[
            {
                "repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1,
                              "startColumnIndex": 0, "endColumnIndex": 6},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": _rgb(0.824, 0.882, 0.953),
                        "textFormat": {"bold": True, "fontSize": 10},
                        "verticalAlignment": "MIDDLE",
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
                }
            }
            for r in [2, 5, recent_start - 1]
        ],
        # Totals row (row 4 = index 3): white bg, bold
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 3, "endRowIndex": 4,
                          "startColumnIndex": 0, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _rgb(0.953, 0.953, 0.953),
                    "textFormat": {"bold": True},
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
            }
        },
        # Column widths for Dashboard
        *[
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sid, "dimension": "COLUMNS",
                              "startIndex": i, "endIndex": i + 1},
                    "properties": {"pixelSize": w},
                    "fields": "pixelSize",
                }
            }
            for i, w in enumerate([160, 110, 110, 140, 80, 40])
        ],
        # Freeze header row
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    sh.batch_update({"requests": requests})


def append_completion_row(row: list) -> None:
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_SERVICE_ACCOUNT_JSON, COMPLETIONS_SHEETS_ID

    creds = Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES)
    gc = gspread.Client(auth=creds)
    sh = gc.open_by_key(COMPLETIONS_SHEETS_ID)

    is_new = False
    try:
        ws = sh.worksheet(_LOG)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(_LOG, rows=2000, cols=len(_COMPLETIONS_HEADERS))
        ws.append_row(_COMPLETIONS_HEADERS, value_input_option="USER_ENTERED")
        is_new = True

    result = ws.append_row(row, value_input_option="USER_ENTERED")
    updated = result.get("updates", {}).get("updatedRange", "")
    m = _re.search(r"[A-Z](\d+):", updated)
    row_idx = int(m.group(1)) if m else None

    if is_new:
        _setup_log_sheet(ws)
        _setup_dashboard(sh)

    if row_idx:
        _format_log_row(ws, row_idx, completed=(row[6] == "Yes"))


def _setup_hw_log_sheet(ws) -> None:
    sid = ws.id
    sh = ws.spreadsheet
    # Column widths: Timestamp, TA Name, Cohort, Event Title, Event Date, Completed, Reason
    col_widths = [175, 120, 130, 220, 110, 100, 290]
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 7},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _rgb(0.129, 0.196, 0.341),
                    "textFormat": {"bold": True, "fontSize": 11,
                                   "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 36},
                "fields": "pixelSize",
            }
        },
    ]
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    sh.batch_update({"requests": requests})


def _format_hw_row(ws, row_idx: int, completed: bool) -> None:
    sid = ws.id
    i = row_idx - 1
    row_bg = _rgb(0.851, 0.957, 0.851) if completed else _rgb(0.988, 0.894, 0.882)
    badge_bg = _rgb(0.204, 0.659, 0.325) if completed else _rgb(0.820, 0.165, 0.118)
    ws.spreadsheet.batch_update({"requests": [
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1,
                          "startColumnIndex": 0, "endColumnIndex": 7},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": row_bg,
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,verticalAlignment)",
            }
        },
        # "Yes"/"No" badge — column F (index 5)
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1,
                          "startColumnIndex": 5, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": badge_bg,
                    "textFormat": {"bold": True, "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
    ]})


def append_hw_check_row(row: list) -> None:
    """Append a HW check result row to the 'HW Checks Log' sheet tab."""
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_SERVICE_ACCOUNT_JSON, COMPLETIONS_SHEETS_ID

    creds = Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES)
    gc = gspread.Client(auth=creds)
    sh = gc.open_by_key(COMPLETIONS_SHEETS_ID)

    is_new = False
    try:
        ws = sh.worksheet(_HW_LOG)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(_HW_LOG, rows=2000, cols=len(_HW_HEADERS))
        ws.append_row(_HW_HEADERS, value_input_option="USER_ENTERED")
        is_new = True

    result = ws.append_row(row, value_input_option="USER_ENTERED")
    updated = result.get("updates", {}).get("updatedRange", "")
    m = _re.search(r"[A-Z](\d+):", updated)
    row_idx = int(m.group(1)) if m else None

    if is_new:
        _setup_hw_log_sheet(ws)

    if row_idx:
        _format_hw_row(ws, row_idx, completed=(row[5] == "Yes"))


_HW_STATS = "TA HW Stats"
_HW_STATS_HEADERS = ["TA Name", "Checks Done", "Yes", "No", "Rate"]


def write_hw_stats_tab(stats: list[dict]) -> None:
    """Overwrite the 'TA HW Stats' tab with current per-TA summary."""
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_SERVICE_ACCOUNT_JSON, COMPLETIONS_SHEETS_ID

    creds = Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES)
    gc = gspread.Client(auth=creds)
    sh = gc.open_by_key(COMPLETIONS_SHEETS_ID)

    try:
        ws = sh.worksheet(_HW_STATS)
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(_HW_STATS, rows=100, cols=5)

    rows = [_HW_STATS_HEADERS]
    for s in stats:
        rows.append([
            s["ta_name"],
            s["total"],
            s["yes_count"],
            s["no_count"],
            f"{s['rate']}%",
        ])
    ws.update(rows, value_input_option="USER_ENTERED")

    sid = ws.id
    n_data = len(stats)
    requests = [
        # Header: dark navy
        {
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _rgb(0.129, 0.196, 0.341),
                    "textFormat": {"bold": True, "fontSize": 11,
                                   "foregroundColor": _rgb(1, 1, 1)},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        },
        # Freeze header
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    # Colour rate column: green ≥ 80%, amber 50–79%, red < 50%
    for i, s in enumerate(stats):
        row_i = i + 1  # 0-based, skip header
        rate = s["rate"]
        if rate >= 80:
            bg = _rgb(0.851, 0.957, 0.851)
        elif rate >= 50:
            bg = _rgb(1.0, 0.957, 0.800)
        else:
            bg = _rgb(0.988, 0.894, 0.882)
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": row_i, "endRowIndex": row_i + 1,
                          "startColumnIndex": 4, "endColumnIndex": 5},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        })
    sh.batch_update({"requests": requests})


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

    all_titles = [ws.title for ws in sh.worksheets()]
    logger.info("Available sheet tabs: %s", all_titles)

    events: list[dict] = []

    try:
        ws = sh.worksheet("[2026] Lectures")
        rows = ws.get_all_values()
        logger.info("2026 Lectures: %d rows. First row: %s", len(rows), rows[0] if rows else [])
        lecture_events = parse_lectures_sheet(rows)
        events.extend(lecture_events)
        logger.info("Parsed %d lecture events.", len(lecture_events))
    except Exception as e:
        logger.error("Failed to parse 2026 Lectures: %s", e)

    try:
        ws = sh.worksheet("[2026] Consults")
        rows = ws.get_all_values()
        logger.info("2026 Consults: %d rows. First 3 rows: %s", len(rows), rows[:3] if rows else [])
        consult_events = parse_consults_grid(rows)
        events.extend(consult_events)
        logger.info("Parsed %d consult events.", len(consult_events))
    except Exception as e:
        logger.error("Failed to parse 2026 Consults: %s", e)

    return events
