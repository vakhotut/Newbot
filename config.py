import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://api.bitaps.com/ltc/v1")
    BOT_MNEMONIC = os.getenv('BOT_MNEMONIC', '')
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/ltc_bot")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: float = float(os.getenv("RETRY_DELAY", "1.0"))
    LTC_NETWORK: str = os.getenv("LTC_NETWORK", "mainnet")

config = Config()
