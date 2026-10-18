import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Asia/Bangkok")


@dataclass(frozen=True)
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    database_url: str
    job_secret: str = ""  # Cloud Scheduler sends this to run scheduled jobs; empty disables them


def get_settings() -> Settings:
    return Settings(
        line_channel_secret=os.environ.get("LINE_CHANNEL_SECRET", ""),
        line_channel_access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./stock_bot.db"),
        job_secret=os.environ.get("JOB_SECRET", ""),
    )
