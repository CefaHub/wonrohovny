from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    bot_token: str
    db_path: str
    sex_duration_seconds: int = 60
    pregnancy_duration_seconds: int = 300
    nausea_check_interval_seconds: int = 30
    nausea_chance_percent: int = 10
    daily_bonus_vrk: int = 150
    normal_gacha_price: int = 250
    elite_gacha_price_vh: int = 35



def load_config() -> Config:
    load_dotenv()
    data_dir = os.getenv("DATA_DIR", ".")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    return Config(
        bot_token=os.getenv("BOT_TOKEN", ""),
        db_path=os.getenv("DB_PATH", str(Path(data_dir) / "bot.db")),
        sex_duration_seconds=int(os.getenv("SEX_DURATION_SECONDS", "60")),
        pregnancy_duration_seconds=int(os.getenv("PREGNANCY_DURATION_SECONDS", "300")),
        nausea_check_interval_seconds=int(os.getenv("NAUSEA_INTERVAL_SECONDS", "30")),
        nausea_chance_percent=int(os.getenv("NAUSEA_CHANCE_PERCENT", "10")),
        daily_bonus_vrk=int(os.getenv("DAILY_BONUS_VRK", "150")),
        normal_gacha_price=int(os.getenv("NORMAL_GACHA_PRICE", "250")),
        elite_gacha_price_vh=int(os.getenv("ELITE_GACHA_PRICE_VH", "35")),
    )
