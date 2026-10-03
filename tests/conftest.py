import os
import sys
import tempfile
from pathlib import Path

# ต้องตั้งค่า Environment ก่อน import config.settings (Settings โหลดค่าตอน import)
_TMP = Path(tempfile.mkdtemp(prefix="trading_bot_tests_"))
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP / 'test.db'}",
    "TEMP_NEWS_DIR": str(_TMP / "temp_news"),
    "GEMINI_API_KEY": "",
    "APP_MODE": "paper",
    "INITIAL_BALANCE": "100000",
    "MAX_RISK_PER_TRADE_PCT": "2.0",
    "STOP_LOSS_PCT": "3.0",
    "TAKE_PROFIT_PCT": "6.0",
    "MAX_DAILY_LOSS_PCT": "5.0",
    "ALLOW_SYNTHETIC_TRADING": "false",
    "RISK_CHECK_INTERVAL_SECONDS": "0",
    "PIPELINE_INTERVAL_MINUTES": "0",
    "ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from datetime import datetime

import pytest

from core.interfaces.data_feed import Quote


@pytest.fixture
def quotes(monkeypatch):
    """ควบคุมราคาที่ data_feed คืนให้: quotes["AAPL"] = 100.0 หรือ None (= ราคาจำลอง)"""
    from core.data.yahoo_feed import data_feed

    prices = {}

    async def fake_quote(symbol: str) -> Quote:
        symbol = symbol.upper()
        price = prices.get(symbol)
        if price is None:
            return Quote(symbol=symbol, price=150.0, timestamp=datetime.utcnow(), is_synthetic=True)
        return Quote(symbol=symbol, price=price, timestamp=datetime.utcnow())

    monkeypatch.setattr(data_feed, "get_latest_quote", fake_quote)
    return prices


@pytest.fixture
async def fresh_state():
    """ล้างฐานข้อมูลและสถานะ Broker ให้เหมือนเริ่มระบบใหม่"""
    from database.db_manager import db_manager
    from database.models import Base
    from core.brokers.paper_broker import broker
    from core.agents.pipeline import pipeline

    await db_manager.engine.dispose()
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    broker.cash_balance = broker.initial_balance
    broker.realized_pnl = 0.0
    broker.positions = {}
    broker.day_start_date = None
    broker.day_start_equity = None
    broker._lock = asyncio.Lock()
    pipeline.stop_event = asyncio.Event()
    yield broker
    await db_manager.engine.dispose()
