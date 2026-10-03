import asyncio
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
    - บันทึกทุกคำสั่งซื้อขายและสถานะบัญชีลงใน SQLite (โหลดกลับเมื่อรีสตาร์ทผ่าน load_state)
    - คุมไม่ให้ซื้อเกินเงินที่มี และไม่ส่งคำสั่งด้วยราคาจำลอง (Synthetic)
    - ทุกคำสั่งทำงานภายใต้ Lock เดียว ป้องกันคำสั่งซ้อนกัน (เช่น Panic Sell ระหว่าง Pipeline ซื้อ)
    """

    def __init__(self, initial_balance: float = settings.INITIAL_BALANCE):
        self.initial_balance = initial_balance
        self.cash_balance = initial_balance
        self.realized_pnl = 0.0
        self.positions: Dict[str, Position] = {}
        self.mode = "paper"
        self.day_start_date: Optional[str] = None
        self.day_start_equity: Optional[float] = None
        self._lock = asyncio.Lock()

    async def load_state(self):
        """โหลดเงินสด, P&L และ Positions จากฐานข้อมูล (เรียกครั้งเดียวตอน Startup)"""
        state = await db_manager.get_account_state()
        stored_positions = await db_manager.get_all_positions()

        self.positions = {
            p["symbol"]: Position(
                symbol=p["symbol"],
                quantity=p["quantity"],
                average_entry_price=p["average_entry_price"],
                current_price=p["current_price"],
                market_value=p["market_value"],
                unrealized_pnl=p["unrealized_pnl"],
                unrealized_pnl_pct=p["unrealized_pnl_pct"],
                stop_loss_price=p["stop_loss_price"],
                take_profit_price=p["take_profit_price"],
            )
            for p in stored_positions
        }

        if state is not None:
            self.cash_balance = state["cash_balance"]
            self.realized_pnl = state["realized_pnl"]
            self.day_start_date = state["day_start_date"]
            self.day_start_equity = state["day_start_equity"]
        else:
            # ฐานข้อมูลจากเวอร์ชันเก่า (ยังไม่มีตาราง account_state): ประมาณเงินสดจากต้นทุนของ Position ที่ค้างอยู่
            cost_basis = sum(p.quantity * p.average_entry_price for p in self.positions.values())
            self.cash_balance = self.initial_balance - cost_basis
            self.realized_pnl = 0.0
            if self.positions:
                logger.warning(
                    "No saved account state found; reconstructed cash from %d open positions "
                    "(realized P&L reset to 0).", len(self.positions)
                )
            await self._persist_account_state()

        logger.info(
            "Paper broker state loaded: cash=%.2f realized_pnl=%.2f positions=%d",
            self.cash_balance, self.realized_pnl, len(self.positions)
        )

    async def _persist_account_state(self):
        await db_manager.save_account_state(
            cash_balance=self.cash_balance,
            realized_pnl=self.realized_pnl,
            day_start_date=self.day_start_date,
            day_start_equity=self.day_start_equity,
        )

    def _trading_blocked_by_synthetic(self, is_synthetic: bool) -> bool:
        return is_synthetic and not settings.ALLOW_SYNTHETIC_TRADING

    async def _refresh_prices(self):
        """อัปเดตราคาตลาดของทุก Position (ข้ามราคาจำลอง เก็บราคาจริงล่าสุดไว้)"""
        symbols = list(self.positions.keys())
        if not symbols:
            return
        quotes = await data_feed.get_batch_quotes(symbols)
        for symbol, quote in quotes.items():
            pos = self.positions.get(symbol)
            if pos is None or quote.is_synthetic:
                continue
            pos.current_price = quote.price
            pos.market_value = round(pos.quantity * quote.price, 2)
            pos.unrealized_pnl = round((quote.price - pos.average_entry_price) * pos.quantity, 2)
            pos.unrealized_pnl_pct = round(
                ((quote.price - pos.average_entry_price) / pos.average_entry_price) * 100, 2
            ) if pos.average_entry_price > 0 else 0.0

    def _build_account(self) -> AccountInfo:
        positions_market_value = sum(p.quantity * p.current_price for p in self.positions.values())
        total_unrealized_pnl = sum(
            (p.current_price - p.average_entry_price) * p.quantity for p in self.positions.values()
        )
        return AccountInfo(
            cash_balance=round(self.cash_balance, 2),
            equity=round(self.cash_balance + positions_market_value, 2),
            portfolio_value=round(positions_market_value, 2),
            unrealized_pnl=round(total_unrealized_pnl, 2),
            realized_pnl=round(self.realized_pnl, 2),
            currency=settings.CURRENCY,
            mode=self.mode
        )

    async def get_account(self) -> AccountInfo:
        """คำนวณและดึงสถานะพอร์ตล่าสุด (อ่านอย่างเดียว ไม่เขียน DB)"""
        await self._refresh_prices()
        return self._build_account()

    async def record_snapshot(self):
        """บันทึก Snapshot พอร์ตลง DB (เรียกหลังมีการเปลี่ยนแปลง ไม่ใช่ทุกครั้งที่อ่าน)"""
        account = self._build_account()
        await db_manager.record_snapshot(
            cash=account.cash_balance,
            equity=account.equity,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl
        )

    async def get_daily_loss_pct(self) -> float:
        """เปอร์เซ็นต์ขาดทุนของวันนี้ (UTC) เทียบกับ Equity ต้นวัน (ค่าบวก = ขาดทุน)"""
        account = await self.get_account()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self.day_start_date != today or not self.day_start_equity:
            self.day_start_date = today
            self.day_start_equity = account.equity
            await self._persist_account_state()
            return 0.0
        return max(0.0, (self.day_start_equity - account.equity) / self.day_start_equity * 100)

    async def get_positions(self) -> List[Position]:
        # อัปเดตราคาล่าสุดก่อนส่งกลับ
        await self._refresh_prices()
        return list(self.positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        symbol = symbol.upper()
        if symbol in self.positions:
            await self._refresh_prices()
            return self.positions.get(symbol)
        return None

    async def _reject(self, order: OrderRequest, order_id: str, symbol: str, message: str) -> OrderResponse:
        logger.warning(f"Order rejected ({order.side.value} {order.quantity} {symbol}): {message}")
        response = OrderResponse(
            order_id=order_id,
            symbol=symbol,
            side=order.side,
            quantity=order.quantity,
            filled_price=0.0,
            status=OrderStatus.REJECTED,
            message=message
        )
        await db_manager.record_order({
            **response.model_dump(),
            "reason": f"{order.reason or ''} | REJECTED: {message}",
            "stop_loss_price": order.stop_loss_price,
            "take_profit_price": order.take_profit_price
        })
        return response

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """ดำเนินการคำสั่งซื้อขายจำลอง"""
        async with self._lock:
            return await self._execute_order(order)

    async def _execute_order(self, order: OrderRequest) -> OrderResponse:
        symbol = order.symbol.upper()
        order_id = f"ord-{uuid.uuid4().hex[:8]}"

        if order.quantity <= 0:
            return await self._reject(order, order_id, symbol, "จำนวนหุ้นต้องมากกว่า 0")

        quote = await data_feed.get_latest_quote(symbol)
        fill_price = quote.price
        if quote.price <= 0 or self._trading_blocked_by_synthetic(quote.is_synthetic):
            held = self.positions.get(symbol)
            if order.side == OrderSide.SELL and held is not None and held.current_price > 0:
                # ขายออกได้เสมอ (เช่น Panic Sell) โดยใช้ราคาจริงล่าสุดที่ทราบของ Position นั้น
                fill_price = held.current_price
                logger.warning(f"No live quote for {symbol}; selling at last known price {fill_price}")
            else:
                return await self._reject(
                    order, order_id, symbol,
                    "ไม่มีราคาตลาดจริงสำหรับหุ้นนี้ (ดึงราคาไม่สำเร็จ) จึงไม่ส่งคำสั่งด้วยราคาจำลอง"
                )

        cost = fill_price * order.quantity

        if order.side == OrderSide.BUY:
            # ตรวจสอบว่าเงินสดพอหรือไม่
            if cost > self.cash_balance:
                return await self._reject(order, order_id, symbol, "เงินสดคงเหลือไม่เพียงพอสำหรับการเปิด Order")

            # หักเงินสด
            self.cash_balance -= cost

            # จัดการ Position
            if symbol in self.positions:
                existing = self.positions[symbol]
                total_qty = existing.quantity + order.quantity
                avg_price = ((existing.average_entry_price * existing.quantity) + cost) / total_qty
                existing.quantity = total_qty
                existing.average_entry_price = round(avg_price, 4)
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
                return await self._reject(order, order_id, symbol, "ไม่มีหุ้นหรือจำนวนที่ต้องการขายมากกว่าที่มีในพอร์ต")

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

        await self._persist_account_state()

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
        await self.record_snapshot()

        logger.info(f"Order executed: {order.side.value} {order.quantity} {symbol} @ {fill_price}")
        return response

    async def update_exit_levels(
        self, symbol: str, stop_loss_price: Optional[float], take_profit_price: Optional[float]
    ) -> bool:
        symbol = symbol.upper()
        async with self._lock:
            pos = self.positions.get(symbol)
            if pos is None:
                return False
            pos.stop_loss_price = stop_loss_price
            pos.take_profit_price = take_profit_price
            await db_manager.save_or_update_position({
                "symbol": symbol,
                "quantity": pos.quantity,
                "average_entry_price": pos.average_entry_price,
                "current_price": pos.current_price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price
            })
            return True

    async def close_position(self, symbol: str, reason: str = "Manual Close") -> Optional[OrderResponse]:
        symbol = symbol.upper()
        async with self._lock:
            if symbol not in self.positions:
                return None
            qty = self.positions[symbol].quantity
            req = OrderRequest(symbol=symbol, side=OrderSide.SELL, quantity=qty, reason=reason)
            return await self._execute_order(req)

    async def close_all_positions(self, reason: str = "Emergency Sell All") -> List[OrderResponse]:
        results = []
        for symbol in list(self.positions.keys()):
            res = await self.close_position(symbol, reason=reason)
            if res:
                results.append(res)
        return results

broker = PaperBroker()
