import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
    API_BASE_URL: str = "https://api.bitaps.com/ltc/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/ltc_bot")
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

config = Config()
