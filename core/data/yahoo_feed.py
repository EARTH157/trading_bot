import asyncio
import logging
import time
import zlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
try:
    import yfinance as yf
except ImportError:
    yf = None

from config.settings import settings
from core.interfaces.data_feed import DataFeedBase, Quote

logger = logging.getLogger(__name__)

class YahooDataFeed(DataFeedBase):
    """Data Feed ดึงข้อมูลแท่งเทียนและราคา Real-time ผ่าน yfinance พร้อมระบบ Indicator

    yfinance เป็น Synchronous Network Call ทั้งหมด จึงรันผ่าน asyncio.to_thread
    เพื่อไม่ให้บล็อก Event Loop ของ Dashboard / WebSocket
    """

    def __init__(self):
        # Cache เฉพาะราคาจริงเท่านั้น (ไม่เก็บราคา Synthetic)
        self._cache: Dict[str, Tuple[float, Quote]] = {}

    @staticmethod
    def _fetch_history_sync(symbol: str, period: str, timeframe: str) -> pd.DataFrame:
        return yf.Ticker(symbol).history(period=period, interval=timeframe)

    @staticmethod
    def _synthetic_history(symbol: str, periods: int = 120) -> pd.DataFrame:
        """สร้างกราฟราคาจำลองสำหรับ Demo แบบ Offline (Deterministic ต่อ Symbol)"""
        dates = pd.date_range(end=datetime.utcnow(), periods=periods, freq="D")
        # ใช้ RNG แยกต่อ Symbol แทน np.random.seed (ไม่กระทบ Global RNG และได้ผลเหมือนเดิมทุกครั้ง)
        rng = np.random.default_rng(zlib.crc32(symbol.encode("utf-8")))
        base_price = 150.0 if symbol != "NVDA" else 120.0
        noise = rng.normal(0, 1.5, size=len(dates))
        prices = base_price + np.cumsum(noise)
        return pd.DataFrame({
            "Open": prices - 0.5,
            "High": prices + 1.2,
            "Low": prices - 1.0,
            "Close": prices,
            "Volume": rng.integers(1000000, 5000000, size=len(dates))
        }, index=dates)

    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "6mo"
    ) -> pd.DataFrame:
        """ดึงข้อมูลราคาแท่งเทียนและคำนวณ Technical Indicators

        DataFrame ที่ได้จะมี df.attrs["synthetic"] = True หากเป็นข้อมูลจำลอง
        ผู้เรียกต้องตรวจสอบก่อนนำไปตัดสินใจเทรด
        """
        df = pd.DataFrame()
        synthetic = False

        if yf is not None:
            try:
                df = await asyncio.to_thread(self._fetch_history_sync, symbol, period, timeframe)
            except Exception as e:
                logger.warning(f"Error fetching historical data from yfinance for {symbol}: {e}")

        # Fallback สร้าง Synthetic Data หากเน็ตเวิร์กมีปัญหา (สำหรับแสดงผลเท่านั้น)
        if df is None or df.empty or len(df) < 10:
            logger.warning(f"No real market data for {symbol}; generating SYNTHETIC data (not for trading).")
            df = self._synthetic_history(symbol)
            synthetic = True

        # จัดระเบียบ Column Names ให้เป็นตัวพิมพ์เล็ก
        df.columns = [c.lower() for c in df.columns]

        # คำนวณ Indicators: EMA20, EMA50, RSI(14)
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

        # คำนวณ RSI แบบ Wilder's Smoothing (alpha = 1/14)
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        # คำนวณ ATR 14 (สำหรับจุด Stop Loss)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift()).abs()
        tr3 = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()

        df.attrs["synthetic"] = synthetic
        return df

    @staticmethod
    def _fetch_quote_sync(symbol: str) -> Optional[Tuple[float, float]]:
        """คืนค่า (ราคาล่าสุด, ราคาปิดวันก่อน) หรือ None หากดึงไม่ได้"""
        ticker = yf.Ticker(symbol)
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info and hasattr(fast_info, "last_price") and fast_info.last_price:
            current_price = float(fast_info.last_price)
            prev_close = getattr(fast_info, "previous_close", current_price) or current_price
            return current_price, float(prev_close)
        df = ticker.history(period="2d", interval="1d")
        if not df.empty:
            return float(df["Close"].iloc[-1]), float(df["Close"].iloc[0])
        return None

    async def get_latest_quote(self, symbol: str) -> Quote:
        """ดึงราคาล่าสุดของหุ้นตัวนั้น

        ลำดับ: Cache สด -> yfinance -> ราคาจริงล่าสุดใน Cache (stale) -> ราคาจำลอง (is_synthetic=True)
        """
        symbol = symbol.upper()
        cached = self._cache.get(symbol)
        if cached and time.monotonic() - cached[0] < settings.QUOTE_CACHE_SECONDS:
            return cached[1]

        fetched: Optional[Tuple[float, float]] = None
        if yf is not None:
            try:
                fetched = await asyncio.to_thread(self._fetch_quote_sync, symbol)
            except Exception as e:
                logger.warning(f"Error getting quote for {symbol}: {e}")

        if fetched and fetched[0] > 0:
            current_price, prev_close = fetched
            change = current_price - prev_close
            quote = Quote(
                symbol=symbol,
                price=round(current_price, 2),
                change=round(change, 2),
                change_pct=round((change / prev_close) * 100, 2) if prev_close else 0.0,
                timestamp=datetime.utcnow()
            )
            self._cache[symbol] = (time.monotonic(), quote)
            return quote

        # ใช้ราคาจริงล่าสุดที่เคยดึงได้ (อาจเก่า แต่เป็นราคาตลาดจริง)
        if cached:
            return cached[1]

        logger.warning(f"No real quote available for {symbol}; returning SYNTHETIC placeholder price.")
        return Quote(
            symbol=symbol,
            price=150.0,
            change=0.0,
            change_pct=0.0,
            timestamp=datetime.utcnow(),
            is_synthetic=True
        )

    async def get_batch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """ดึงราคาหลายตัวพร้อมกัน"""
        quotes = await asyncio.gather(*(self.get_latest_quote(sym) for sym in symbols))
        return dict(zip(symbols, quotes))

data_feed = YahooDataFeed()
