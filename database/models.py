from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), unique=True, index=True)
    symbol = Column(String(20), index=True)
    side = Column(String(10))  # BUY, SELL
    quantity = Column(Float)
    price = Column(Float)
    order_type = Column(String(20), default="MARKET")
    status = Column(String(20))  # FILLED, CANCELLED, REJECTED
    stop_loss_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PositionModel(Base):
    __tablename__ = "positions"

    symbol = Column(String(20), primary_key=True)
    quantity = Column(Float)
    average_entry_price = Column(Float)
    current_price = Column(Float)
    stop_loss_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cash_balance = Column(Float)
    equity = Column(Float)
    realized_pnl = Column(Float)
    unrealized_pnl = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

class AccountStateModel(Base):
    """สถานะบัญชี Paper Trading (มีแถวเดียว id=1) เพื่อให้พอร์ตไม่หายเมื่อรีสตาร์ท"""
    __tablename__ = "account_state"

    id = Column(Integer, primary_key=True)
    cash_balance = Column(Float)
    realized_pnl = Column(Float, default=0.0)
    # Circuit Breaker: Equity ณ ต้นวัน (UTC) ใช้คำนวณขาดทุนรายวัน
    day_start_date = Column(String(10), nullable=True)  # YYYY-MM-DD
    day_start_equity = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AgentLogModel(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), index=True)
    status = Column(String(20))  # SUCCESS, WARNING, ERROR
    summary = Column(Text)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
