from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Config:
    bot_token: str
    db_path: str
    default_pregnancy_chance: int = 10
    sex_duration_seconds: int = 60
    pregnancy_duration_seconds: int = 300
    nausea_check_interval_seconds: int = 30
    nausea_chance_percent: int = 10


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data" if Path("/app").exists() else BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    db_path = os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.db"))
    return Config(bot_token=token, db_path=db_path)
