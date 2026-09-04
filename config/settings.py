from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # App Mode: 'paper', 'alpaca_paper', 'alpaca_live', 'settrade'
    APP_MODE: str = "paper"

    # Web Dashboard Server
    DASHBOARD_HOST: str = "127.0.0.1"
    DASHBOARD_PORT: int = 8000
    SECRET_KEY: str = "trading_bot_secret_key_12345"

    # AI Models (Gemini)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Watchlist
    WATCHLIST: str = "AAPL,NVDA,MSFT,TSLA,AMZN"

    # Paper Trading Initial Balance
    INITIAL_BALANCE: float = 100000.0
    CURRENCY: str = "USD"

    # Risk Management Rules
    MAX_RISK_PER_TRADE_PCT: float = 2.0  # เสี่ยงไม่เกิน 2% ของพอร์ตต่อเทรด
    STOP_LOSS_PCT: float = 3.0           # ตัดขาดทุนเมื่อติดลบ 3%
    TAKE_PROFIT_PCT: float = 6.0         # ทำกำไรเมื่อบวก 6% (Risk-Reward 1:2)
    MAX_DAILY_LOSS_PCT: float = 5.0      # ขาดทุนรวมต่อวันไม่เกิน 5% (Circuit Breaker)

    # Temporary News Directory
    TEMP_NEWS_DIR: Path = BASE_DIR / "data" / "temp_news"

    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/database/trading.db"

    # Alpaca Settings (Optional)
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_IS_PAPER: bool = True

    # SETTRADE Settings (Optional)
    SETTRADE_APP_ID: str = ""
    SETTRADE_APP_SECRET: str = ""
    SETTRADE_BROKER_ID: str = "000"
    SETTRADE_ACCOUNT_NO: str = ""

    # Notifications (Optional)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    LINE_NOTIFY_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def watchlist_symbols(self) -> List[str]:
        return [sym.strip().upper() for sym in self.WATCHLIST.split(",") if sym.strip()]

settings = Settings()
