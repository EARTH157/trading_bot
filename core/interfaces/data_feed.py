from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel
import pandas as pd

class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class Quote(BaseModel):
    symbol: str
    price: float
    change: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    timestamp: datetime

class DataFeedBase(ABC):
    """Abstract Base Class สำหรับ Data Feed (ดึงราคาหุ้นและกราฟแท่งเทียน)"""

    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1d",
        period: str = "3mo"
    ) -> pd.DataFrame:
        """
        ดึงข้อมูลแท่งเทียนย้อนหลัง (OHLCV)
        คืนค่าเป็น pandas DataFrame ที่มีคอลัมน์: open, high, low, close, volume
        """
        pass

    @abstractmethod
    async def get_latest_quote(self, symbol: str) -> Quote:
        """ดึงราคาล่าสุดของหุ้น"""
        pass

    @abstractmethod
    async def get_batch_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """ดึงราคาล่าสุดของหุ้นหลายๆ ตัวพร้อมกัน"""
        pass
