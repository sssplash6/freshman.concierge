# config.py
import json
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID: int = int(_require("ADMIN_CHAT_ID"))
GOOGLE_SHEETS_ID: str = _require("GOOGLE_SHEETS_ID")
GOOGLE_SERVICE_ACCOUNT_JSON: dict = json.loads(_require("GOOGLE_SERVICE_ACCOUNT_JSON"))
DB_PATH: str = os.getenv("DB_PATH", "/tmp/concierge_bot.db")
SYNC_INTERVAL_HOURS: int = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
TIMEZONE: str = "Asia/Tashkent"  # GMT+5

STAFF_IDS: dict[int, str] = {
    8384175592: "Sanjar",
    7926199790: "Valera",
    5012452972: "Sega",
    744979646:  "Sega",
    7185151344: "Rustam",
    907955385:  "Nigel",
    1378248439: "Lyusyena",
    8115552659: "Tyler",
    433396623:  "Alisher",
    791356497:  "Gulrukh",
}

STAFF_ID_BY_NAME: dict[str, int] = {name: uid for uid, name in STAFF_IDS.items()}

REMIND_IDS: frozenset[int] = frozenset(uid for uid, name in STAFF_IDS.items() if name == "Sega")
