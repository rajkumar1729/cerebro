"""Application calendar helpers; review dates follow the user's local timezone."""
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

_timezone = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


def today() -> date:
    return datetime.now(_timezone).date()
