from pathlib import Path
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# โหมดที่มี Broker Implementation จริงในโค้ดตอนนี้ (Alpaca / Settrade ยังไม่ได้ทำ)
SUPPORTED_APP_MODES = {"paper"}

class Settings(BaseSettings):
    # App Mode: ปัจจุบันรองรับเฉพาะ 'paper' (Alpaca / Settrade ยังไม่ได้ Implement)
    APP_MODE: str = "paper"

    # Web Dashboard Server
    DASHBOARD_HOST: str = "127.0.0.1"
    DASHBOARD_PORT: int = 8000
    DASHBOARD_RELOAD: bool = False  # เปิดเฉพาะตอนพัฒนา (Auto-reload เมื่อแก้โค้ด)
    # Hostnames ที่อนุญาตให้เข้าถึง Dashboard (ป้องกัน DNS Rebinding)
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

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

    # อนุญาตให้เทรดด้วยราคาจำลอง (Synthetic) เมื่อดึงราคาจริงไม่ได้ — ใช้สำหรับ Demo แบบ Offline เท่านั้น
    ALLOW_SYNTHETIC_TRADING: bool = False

    # Scheduler
    PIPELINE_INTERVAL_MINUTES: int = 0     # รัน Pipeline อัตโนมัติทุกกี่นาที (0 = รันด้วยมือเท่านั้น)
    RISK_CHECK_INTERVAL_SECONDS: int = 60  # ตรวจ Stop Loss / Take Profit ทุกกี่วินาที (0 = ปิด)
    QUOTE_CACHE_SECONDS: int = 15          # Cache ราคาล่าสุดเพื่อไม่ยิง Yahoo ถี่เกินไป

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

    @field_validator("APP_MODE")
    @classmethod
    def _validate_app_mode(cls, v: str) -> str:
        mode = v.strip().lower()
        if mode not in SUPPORTED_APP_MODES:
            raise ValueError(
                f"APP_MODE='{v}' ยังไม่รองรับ (รองรับเฉพาะ: {', '.join(sorted(SUPPORTED_APP_MODES))}). "
                "ระบบจะไม่เริ่มทำงานเพื่อป้องกันความเข้าใจผิดว่ากำลังเทรดจริง"
            )
        return mode

    @property
    def allowed_hosts(self) -> List[str]:
        hosts = {h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()}
        hosts.add(self.DASHBOARD_HOST)
        return sorted(hosts)

    @property
    def watchlist_symbols(self) -> List[str]:
        return [sym.strip().upper() for sym in self.WATCHLIST.split(",") if sym.strip()]

settings = Settings()
