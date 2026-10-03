import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, desc, delete

from config.settings import settings
from database.models import Base, OrderModel, PositionModel, PortfolioSnapshotModel, AgentLogModel, AccountStateModel

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_url: str = settings.DATABASE_URL):
        self.engine = create_async_engine(db_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def init_db(self):
        """สร้างตารางในฐานข้อมูลทั้งหมดหากยังไม่มี"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully.")

    async def record_order(self, order_data: Dict[str, Any]) -> OrderModel:
        """บันทึกประวัติการส่งคำสั่งซื้อขาย"""
        async with self.session_factory() as session:
            order = OrderModel(
                order_id=order_data["order_id"],
                symbol=order_data["symbol"],
                side=order_data["side"],
                quantity=order_data["quantity"],
                price=order_data["filled_price"],
                order_type=order_data.get("order_type", "MARKET"),
                status=order_data["status"],
                stop_loss_price=order_data.get("stop_loss_price"),
                take_profit_price=order_data.get("take_profit_price"),
                reason=order_data.get("reason", "")
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            return order

    async def save_or_update_position(self, pos_data: Dict[str, Any]):
        """อัปเดตหรือลบ Position ในฐานข้อมูล"""
        async with self.session_factory() as session:
            stmt = select(PositionModel).where(PositionModel.symbol == pos_data["symbol"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if pos_data["quantity"] <= 0:
                if existing:
                    await session.delete(existing)
                    await session.commit()
                return

            if existing:
                existing.quantity = pos_data["quantity"]
                existing.average_entry_price = pos_data["average_entry_price"]
                existing.current_price = pos_data["current_price"]
                existing.stop_loss_price = pos_data.get("stop_loss_price")
                existing.take_profit_price = pos_data.get("take_profit_price")
                existing.updated_at = datetime.utcnow()
            else:
                new_pos = PositionModel(
                    symbol=pos_data["symbol"],
                    quantity=pos_data["quantity"],
                    average_entry_price=pos_data["average_entry_price"],
                    current_price=pos_data["current_price"],
                    stop_loss_price=pos_data.get("stop_loss_price"),
                    take_profit_price=pos_data.get("take_profit_price"),
                )
                session.add(new_pos)
            await session.commit()

    async def get_all_positions(self) -> List[Dict[str, Any]]:
        """ดึงรายการ Positions ทั้งหมดที่เปิดอยู่"""
        async with self.session_factory() as session:
            stmt = select(PositionModel)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "symbol": r.symbol,
                    "quantity": r.quantity,
                    "average_entry_price": r.average_entry_price,
                    "current_price": r.current_price,
                    "market_value": r.quantity * r.current_price,
                    "unrealized_pnl": (r.current_price - r.average_entry_price) * r.quantity,
                    "unrealized_pnl_pct": ((r.current_price - r.average_entry_price) / r.average_entry_price * 100) if r.average_entry_price > 0 else 0,
                    "stop_loss_price": r.stop_loss_price,
                    "take_profit_price": r.take_profit_price
                }
                for r in rows
            ]

    async def get_recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """ดึงรายการ Order ล่าสุด"""
        async with self.session_factory() as session:
            stmt = select(OrderModel).order_by(desc(OrderModel.created_at)).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "order_id": r.order_id,
                    "symbol": r.symbol,
                    "side": r.side,
                    "quantity": r.quantity,
                    "price": r.price,
                    "status": r.status,
                    "stop_loss_price": r.stop_loss_price,
                    "take_profit_price": r.take_profit_price,
                    "reason": r.reason,
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
                }
                for r in rows
            ]

    async def get_account_state(self) -> Optional[Dict[str, Any]]:
        """ดึงสถานะบัญชีที่บันทึกไว้ (None หากยังไม่เคยบันทึก)"""
        async with self.session_factory() as session:
            row = await session.get(AccountStateModel, 1)
            if row is None:
                return None
            return {
                "cash_balance": row.cash_balance,
                "realized_pnl": row.realized_pnl or 0.0,
                "day_start_date": row.day_start_date,
                "day_start_equity": row.day_start_equity,
            }

    async def save_account_state(self, **fields: Any):
        """บันทึก/อัปเดตสถานะบัญชี (เฉพาะฟิลด์ที่ส่งมา)"""
        async with self.session_factory() as session:
            row = await session.get(AccountStateModel, 1)
            if row is None:
                row = AccountStateModel(id=1)
                session.add(row)
            for key, value in fields.items():
                setattr(row, key, value)
            await session.commit()

    async def record_snapshot(self, cash: float, equity: float, realized_pnl: float, unrealized_pnl: float):
        """บันทึกภาพรวมสถานะพอร์ตรายช่วงเวลา"""
        async with self.session_factory() as session:
            snapshot = PortfolioSnapshotModel(
                cash_balance=cash,
                equity=equity,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl
            )
            session.add(snapshot)
            await session.commit()

    async def log_agent(self, agent_name: str, status: str, summary: str, details: Dict[str, Any] = None):
        """บันทึก Log การวิเคราะห์ของ AI แต่ละตัว"""
        async with self.session_factory() as session:
            log_entry = AgentLogModel(
                agent_name=agent_name,
                status=status,
                summary=summary,
                details_json=json.dumps(details, ensure_ascii=False) if details else "{}"
            )
            session.add(log_entry)
            await session.commit()

    async def get_recent_agent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """ดึงบันทึก Log ของ AI ล่าสุด"""
        async with self.session_factory() as session:
            stmt = select(AgentLogModel).order_by(desc(AgentLogModel.created_at)).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "agent_name": r.agent_name,
                    "status": r.status,
                    "summary": r.summary,
                    "details": json.loads(r.details_json) if r.details_json else {},
                    "created_at": r.created_at.strftime("%H:%M:%S") if r.created_at else ""
                }
                for r in rows
            ]

db_manager = DatabaseManager()
