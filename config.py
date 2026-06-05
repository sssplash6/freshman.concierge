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
# Destination for the Completions Log / Dashboard tabs. Defaults to the main
# sheet if unset, so existing deployments keep working.
COMPLETIONS_SHEETS_ID: str = os.getenv("COMPLETIONS_SHEETS_ID", "").strip() or GOOGLE_SHEETS_ID
GOOGLE_SERVICE_ACCOUNT_JSON: dict = json.loads(_require("GOOGLE_SERVICE_ACCOUNT_JSON"))
DB_PATH: str = os.getenv("DB_PATH", "/tmp/concierge_bot.db")
SYNC_INTERVAL_HOURS: int = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
TIMEZONE: str = "Asia/Tashkent"  # GMT+5

STAFF_IDS: dict[int, str] = {
    8384175592: "Sanjar",
    7926199790: "Valera",
    5012452972: "Sega",
    8836861446: "Sega",  # Sega's primary account — full admin via REMIND_IDS
    1183676997: "Rustam",
    907955385:  "Nigel",
    1378248439: "Lyusyena",
    8115552659: "Tyler",
    433396623:  "Alisher",
    791356497:  "Gulrukh",
}

STAFF_IDS.update(TA_IDS)

STAFF_ID_BY_NAME: dict[str, int] = {name: uid for uid, name in STAFF_IDS.items()}

REMIND_IDS: frozenset[int] = frozenset(uid for uid, name in STAFF_IDS.items() if name == "Sega")

# Maps cohort name → Telegram group chat ID. Set via COHORT_GROUP_CHATS env var as JSON.
# Example: '{"April Offline": -1001234567890, "May Online": -1009876543210}'
COHORT_GROUP_CHATS: dict[str, int] = {
    k: int(v) for k, v in json.loads(os.getenv("COHORT_GROUP_CHATS", "{}")).items()
}

# TA names available for cohort assignment. Update with real names/IDs when TAs onboard.
TA_NAMES: list[str] = ["a", "b", "c", "d"]

# TA Telegram IDs → display name. Add real IDs here so TAs can register with /start.
TA_IDS: dict[int, str] = {
    int(uid): name
    for uid, name in json.loads(os.getenv("TA_IDS", "{}")).items()
}
