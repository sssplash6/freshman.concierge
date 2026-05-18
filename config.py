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

KNOWN_NAMES: list[str] = [
    "Tyler", "Valera", "Rustam", "Nigel", "Sega",
    "Sanjar", "Lyusyena", "Alisher", "Madina", "Komron",
]
