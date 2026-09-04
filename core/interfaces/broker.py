from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    reason: Optional[str] = "AI Signal"

class OrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    filled_price: float
    status: OrderStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: Optional[str] = None

class Position(BaseModel):
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

class AccountInfo(BaseModel):
    cash_balance: float
    equity: float
    portfolio_value: float
    unrealized_pnl: float
    realized_pnl: float
    currency: str = "USD"
    mode: str = "paper"

class BrokerBase(ABC):
    """Abstract Base Class สำหรับ Broker Adapter (Paper, Alpaca, Settrade)"""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """ดึงข้อมูลบัญชี พอร์ต และเงินสดคงเหลือ"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """ดึงรายการหุ้นทั้งหมดที่ถืออยู่ในพอร์ต"""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """ดึงรายการหุ้นตัวใดตัวหนึ่ง"""
        pass

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """ส่งคำสั่งซื้อหรือขาย"""
        pass

    @abstractmethod
    async def close_position(self, symbol: str, reason: str = "Manual Close") -> Optional[OrderResponse]:
        """ปิดออเดอร์หุ้นทั้งหมดในสัญลักษณ์ที่ระบุ"""
        pass

    @abstractmethod
    async def close_all_positions(self, reason: str = "Emergency Sell All") -> List[OrderResponse]:
        """Panic Button: ขายหุ้นทุกตัวในพอร์ตทันที"""
        pass
