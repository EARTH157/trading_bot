import uuid
import logging
from typing import List, Optional, Dict
from datetime import datetime

from config.settings import settings
from core.interfaces.broker import (
    BrokerBase, OrderRequest, OrderResponse, OrderSide, OrderStatus, Position, AccountInfo
)
from core.data.yahoo_feed import data_feed
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class PaperBroker(BrokerBase):
    """
    จำลองการซื้อขายเสมือนจริง (Paper Trading Broker)
    - คำนวณเงินสด (Cash Balance), มูลค่าพอร์ต (Equity)
    - บันทึกทุกคำสั่งซื้อขายลงใน SQLite
    - คุมไม่ให้ซื้อเกินเงินที่มี
    """

    def __init__(self, initial_balance: float = settings.INITIAL_BALANCE):
        self.cash_balance = initial_balance
        self.realized_pnl = 0.0
        self.positions: Dict[str, Position] = {}
        self.mode = "paper"

    async def get_account(self) -> AccountInfo:
        """คำนวณและดึงสถานะพอร์ตล่าสุด"""
        positions_market_value = 0.0
        total_unrealized_pnl = 0.0

        # อัปเดตราคาตลาดปัจจุบันของทุกหุ้นในพอร์ต
        for symbol, pos in list(self.positions.items()):
            quote = await data_feed.get_latest_quote(symbol)
            pos.current_price = quote.price
            pos.market_value = round(pos.quantity * quote.price, 2)
            pos.unrealized_pnl = round((quote.price - pos.average_entry_price) * pos.quantity, 2)
            pos.unrealized_pnl_pct = round(
                ((quote.price - pos.average_entry_price) / pos.average_entry_price) * 100, 2
            ) if pos.average_entry_price > 0 else 0.0

            positions_market_value += pos.market_value
            total_unrealized_pnl += pos.unrealized_pnl

        equity = round(self.cash_balance + positions_market_value, 2)

        # บันทึก Snapshot ลง DB
        await db_manager.record_snapshot(
            cash=self.cash_balance,
            equity=equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=total_unrealized_pnl
        )

        return AccountInfo(
            cash_balance=round(self.cash_balance, 2),
            equity=equity,
            portfolio_value=round(positions_market_value, 2),
            unrealized_pnl=round(total_unrealized_pnl, 2),
            realized_pnl=round(self.realized_pnl, 2),
            currency=settings.CURRENCY,
            mode=self.mode
        )

    async def get_positions(self) -> List[Position]:
        # อัปเดตราคาล่าสุดก่อนส่งกลับ
        await self.get_account()
        return list(self.positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        symbol = symbol.upper()
        if symbol in self.positions:
            await self.get_account()
            return self.positions.get(symbol)
        return None

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """ดำเนินการคำสั่งซื้อขายจำลอง"""
        symbol = order.symbol.upper()
        quote = await data_feed.get_latest_quote(symbol)
        fill_price = quote.price if quote.price > 0 else 100.0

        order_id = f"ord-{uuid.uuid4().hex[:8]}"
        cost = fill_price * order.quantity

        if order.side == OrderSide.BUY:
            # ตรวจสอบว่าเงินสดพอหรือไม่
            if cost > self.cash_balance:
                logger.warning(f"Insufficient funds: cost {cost:.2f} > cash {self.cash_balance:.2f}")
                response = OrderResponse(
                    order_id=order_id,
                    symbol=symbol,
                    side=order.side,
                    quantity=order.quantity,
                    filled_price=0.0,
                    status=OrderStatus.REJECTED,
                    message="เงินสดคงเหลือไม่เพียงพอสำหรับการเปิด Order"
                )
                await db_manager.record_order({
                    **response.model_dump(),
                    "reason": order.reason or "Insufficient funds",
                    "stop_loss_price": order.stop_loss_price,
                    "take_profit_price": order.take_profit_price
                })
                return response

            # หักเงินสด
            self.cash_balance -= cost

            # จัดการ Position
            if symbol in self.positions:
                existing = self.positions[symbol]
                total_qty = existing.quantity + order.quantity
                avg_price = ((existing.average_entry_price * existing.quantity) + cost) / total_qty
                existing.quantity = total_qty
                existing.average_entry_price = round(avg_price, 2)
                existing.current_price = fill_price
                existing.stop_loss_price = order.stop_loss_price or existing.stop_loss_price
                existing.take_profit_price = order.take_profit_price or existing.take_profit_price
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=order.quantity,
                    average_entry_price=fill_price,
                    current_price=fill_price,
                    market_value=cost,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    stop_loss_price=order.stop_loss_price,
                    take_profit_price=order.take_profit_price
                )

            # บันทึกลงฐานข้อมูล
            await db_manager.save_or_update_position({
                "symbol": symbol,
                "quantity": self.positions[symbol].quantity,
                "average_entry_price": self.positions[symbol].average_entry_price,
                "current_price": fill_price,
                "stop_loss_price": self.positions[symbol].stop_loss_price,
                "take_profit_price": self.positions[symbol].take_profit_price
            })

        elif order.side == OrderSide.SELL:
            if symbol not in self.positions or self.positions[symbol].quantity < order.quantity:
                logger.warning(f"Cannot sell {symbol}: position not found or quantity exceeded")
                response = OrderResponse(
                    order_id=order_id,
                    symbol=symbol,
                    side=order.side,
                    quantity=order.quantity,
                    filled_price=0.0,
                    status=OrderStatus.REJECTED,
                    message="ไม่มีหุ้นหรือจำนวนที่ต้องการขายมากกว่าที่มีในพอร์ต"
                )
                return response

            pos = self.positions[symbol]
            pnl = (fill_price - pos.average_entry_price) * order.quantity
            self.realized_pnl += pnl
            self.cash_balance += cost

            pos.quantity -= order.quantity
            if pos.quantity <= 0:
                del self.positions[symbol]
                await db_manager.save_or_update_position({"symbol": symbol, "quantity": 0})
            else:
                await db_manager.save_or_update_position({
                    "symbol": symbol,
                    "quantity": pos.quantity,
                    "average_entry_price": pos.average_entry_price,
                    "current_price": fill_price,
                    "stop_loss_price": pos.stop_loss_price,
                    "take_profit_price": pos.take_profit_price
                })

        response = OrderResponse(
            order_id=order_id,
            symbol=symbol,
            side=order.side,
            quantity=order.quantity,
            filled_price=fill_price,
            status=OrderStatus.FILLED,
            message="Order executed successfully"
        )

        await db_manager.record_order({
            **response.model_dump(),
            "reason": order.reason or "AI Signal Execution",
            "stop_loss_price": order.stop_loss_price,
            "take_profit_price": order.take_profit_price
        })

        logger.info(f"Order executed: {order.side} {order.quantity} {symbol} @ {fill_price}")
        return response

    async def close_position(self, symbol: str, reason: str = "Manual Close") -> Optional[OrderResponse]:
        symbol = symbol.upper()
        if symbol in self.positions:
            qty = self.positions[symbol].quantity
            req = OrderRequest(symbol=symbol, side=OrderSide.SELL, quantity=qty, reason=reason)
            return await self.place_order(req)
        return None

    async def close_all_positions(self, reason: str = "Emergency Sell All") -> List[OrderResponse]:
        results = []
        for symbol in list(self.positions.keys()):
            res = await self.close_position(symbol, reason=reason)
            if res:
                results.append(res)
        return results

broker = PaperBroker()
