import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    sheet_id: str
    credentials_file: Path
    state_dir: Path
    allowed_user_ids: frozenset[int]
    closing_time: time

    @property
    def sheet_url(self) -> str:
        return (
            "https://docs.google.com/spreadsheets/d/"
            f"{self.sheet_id}/edit"
        )


def load_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    allowed = os.getenv("ALLOWED_USER_IDS", "")
    try:
        user_ids = []
        for value in allowed.split(","):
            value = value.strip()
            if value:
                user_ids.append(int(value))
        users = frozenset(user_ids)
        hour_text, minute_text = os.getenv(
            "CLOSE_TIME", "00:00"
        ).split(":")
        hour = int(hour_text)
        minute = int(minute_text)
        closing_time = time(hour, minute, tzinfo=ARGENTINA)
    except ValueError as error:
        raise ValueError(
            "Invalid user IDs or CLOSE_TIME"
        ) from error
    credentials_file = PROJECT_ROOT / os.getenv(
        "GOOGLE_CREDENTIALS_FILE", "credentials.json"
    )
    state_dir = PROJECT_ROOT / os.getenv("STATE_DIR", ".state")
    if not token or not sheet_id or not users:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN, GOOGLE_SHEET_ID and "
            "ALLOWED_USER_IDS are required"
        )
    if any(user <= 0 for user in users):
        raise ValueError("Allowed user IDs must be positive")
    if not credentials_file.is_file():
        raise ValueError(
            "Google credentials file does not exist"
        )
    return Config(
        token,
        sheet_id,
        credentials_file,
        state_dir,
        users,
        closing_time,
    )
