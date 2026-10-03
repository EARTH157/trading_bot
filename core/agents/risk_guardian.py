import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
import math

from config.settings import settings
from core.interfaces.agent_base import AgentBase, AgentExecutionResult
from core.interfaces.broker import OrderRequest, OrderSide, OrderType, OrderStatus
from core.brokers.paper_broker import broker
from core.data.yahoo_feed import data_feed
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class RiskExecutionAgent(AgentBase):
    """
    🛡️ Agent 4: Risk & Execution Guardian
    - หน้าที่: ผู้พิทักษ์ความปลอดภัยทางการเงินและส่งคำสั่งซื้อขายอย่างระมัดระวัง
    - คำนวณ Position Sizing (เสี่ยงไม่เกิน MAX_RISK_PER_TRADE_PCT ของพอร์ตต่อเทรด และลงทุนไม่เกิน 20% ต่อตัว)
    - บังคับตั้งราคา Stop Loss (เช่น -3%) และ Take Profit (+6%) จากราคาที่ซื้อได้จริง
    - มีระบบ Circuit Breaker หยุดเปิด Position ใหม่เมื่อขาดทุนรายวันถึง MAX_DAILY_LOSS_PCT
    - ตรวจสอบความถูกต้องก่อนส่งคำสั่งไปยัง Broker
    """

    def __init__(self):
        super().__init__(
            name="Agent-4: Risk & Execution Guardian",
            role="ควบคุมความเสี่ยง คำนวณขนาดไม้ และตัดสินใจส่งคำสั่งอย่างระมัดระวัง"
        )
        self.max_positions = 5
        self.max_allocation_per_stock_pct = 20.0  # ลงทุนไม่เกิน 20% ของพอร์ตต่อตัวเดียว

    @staticmethod
    def exit_levels(entry_price: float) -> Tuple[float, float]:
        """คำนวณราคา Stop Loss / Take Profit จากราคาเข้าซื้อ"""
        stop_loss_price = round(entry_price * (1 - settings.STOP_LOSS_PCT / 100.0), 2)
        take_profit_price = round(entry_price * (1 + settings.TAKE_PROFIT_PCT / 100.0), 2)
        return stop_loss_price, take_profit_price

    def position_size(self, equity: float, price: float) -> int:
        """จำนวนหุ้นที่ซื้อได้: น้อยกว่าระหว่าง (ความเสี่ยงต่อไม้ / ระยะ Stop) และ (เพดานเงินลงทุนต่อตัว / ราคา)"""
        if price <= 0 or equity <= 0:
            return 0
        risk_amount = equity * (settings.MAX_RISK_PER_TRADE_PCT / 100.0)
        stop_loss_dist = price * (settings.STOP_LOSS_PCT / 100.0)
        risk_based_qty = risk_amount / stop_loss_dist if stop_loss_dist > 0 else 0.0
        capital_based_qty = equity * (self.max_allocation_per_stock_pct / 100.0) / price
        return math.floor(min(risk_based_qty, capital_based_qty))

    async def enforce_exits(self, screening_results: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """ตรวจ Stop Loss / Take Profit (และสัญญาณ SELL ถ้ามี) ของทุก Position ที่เปิดอยู่

        ใช้ทั้งใน Pipeline และใน Background Risk Monitor ที่รันเป็นระยะ
        """
        executed: List[str] = []
        for pos in await broker.get_positions():
            sym = pos.symbol
            if pos.stop_loss_price and pos.current_price <= pos.stop_loss_price:
                logger.info(f"Triggering Stop Loss for {sym} @ {pos.current_price} <= {pos.stop_loss_price}")
                res = await broker.close_position(sym, reason="Hit Stop Loss")
                if res:
                    executed.append(f"SELL (Stop Loss) {sym}: {res.message}")
                continue

            if pos.take_profit_price and pos.current_price >= pos.take_profit_price:
                logger.info(f"Triggering Take Profit for {sym} @ {pos.current_price} >= {pos.take_profit_price}")
                res = await broker.close_position(sym, reason="Hit Take Profit")
                if res:
                    executed.append(f"SELL (Take Profit) {sym}: {res.message}")
                continue

            item = next((x for x in (screening_results or []) if x["symbol"] == sym), None)
            if item and item["recommendation"] == "SELL":
                res = await broker.close_position(sym, reason=f"Market Screener Signal SELL ({item['combined_score']})")
                if res:
                    executed.append(f"SELL (AI Signal) {sym}: {res.message}")
        return executed

    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        screening_results: List[Dict[str, Any]] = context.get("screening_results", [])
        stop_event: Optional[asyncio.Event] = context.get("stop_event")
        rejected_reasons: List[str] = []

        # 1. จัดการ Position เดิมที่มีอยู่ก่อน (Stop Loss / Take Profit / Sell Signal)
        executed_orders: List[str] = await self.enforce_exits(screening_results)

        # 2. Circuit Breaker: ขาดทุนรายวันถึงลิมิต -> หยุดเปิด Position ใหม่
        daily_loss_pct = await broker.get_daily_loss_pct()
        halted_reason: Optional[str] = None
        if daily_loss_pct >= settings.MAX_DAILY_LOSS_PCT:
            halted_reason = (
                f"Circuit Breaker: ขาดทุนวันนี้ {daily_loss_pct:.2f}% ถึงลิมิต "
                f"{settings.MAX_DAILY_LOSS_PCT}% หยุดเปิด Position ใหม่จนถึงวันถัดไป"
            )
        elif stop_event is not None and stop_event.is_set():
            halted_reason = "ผู้ใช้กด Panic / Stop ระหว่างรอบการทำงาน ยกเลิกการเปิด Position ใหม่"

        if halted_reason:
            logger.warning(halted_reason)
            rejected_reasons.append(halted_reason)
        else:
            # ดึงสถานะบัญชีล่าสุดหลังปิด Order
            account = await broker.get_account()
            current_holdings = {p.symbol for p in await broker.get_positions()}
            cash_available = account.cash_balance

            # 3. พิจารณาเปิด Position ใหม่สำหรับ BUY Candidates
            for candidate in screening_results:
                if candidate["recommendation"] != "BUY":
                    continue
                if stop_event is not None and stop_event.is_set():
                    rejected_reasons.append("ผู้ใช้กด Panic / Stop ระหว่างรอบการทำงาน ยกเลิกคำสั่งซื้อที่เหลือ")
                    break

                sym = candidate["symbol"]

                # กฎความปลอดภัย 1: ไม่เปิดหุ้นตัวเดิมซ้ำซ้อนถ้าถืออยู่แล้ว
                if sym in current_holdings:
                    rejected_reasons.append(f"{sym}: ถือครองอยู่แล้วในพอร์ต ไม่ซื้อเพิ่มเพื่อกระจายความเสี่ยง")
                    continue

                # กฎความปลอดภัย 2: จำนวนหุ้นในพอร์ตต้องไม่เกินพิกัดกระจายความเสี่ยง
                if len(current_holdings) >= self.max_positions:
                    rejected_reasons.append(f"{sym}: พอร์ตถือครบ {self.max_positions} ตัวแล้ว ปฏิเสธการเปิดเพิ่ม")
                    break

                # ใช้ราคาตลาดล่าสุด (ไม่ใช่ราคาปิดรายวันจาก Screener) ในการคำนวณขนาดไม้
                quote = await data_feed.get_latest_quote(sym)
                if quote.is_synthetic and not settings.ALLOW_SYNTHETIC_TRADING:
                    rejected_reasons.append(f"{sym}: ไม่มีราคาตลาดจริง ไม่ส่งคำสั่งซื้อ")
                    continue
                price = quote.price

                target_qty = self.position_size(account.equity, price)
                cost = target_qty * price

                # กฎความปลอดภัย 3: ต้องมีเงินสดจริงพอจ่าย
                if target_qty <= 0 or cost > cash_available:
                    rejected_reasons.append(f"{sym}: เงินสดคงเหลือ ({cash_available:.2f}) ไม่พอซื้อจำนวน {target_qty} หุ้น (ต้องการ {cost:.2f})")
                    continue

                stop_loss_price, take_profit_price = self.exit_levels(price)
                req = OrderRequest(
                    symbol=sym,
                    side=OrderSide.BUY,
                    quantity=float(target_qty),
                    order_type=OrderType.MARKET,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                    reason=f"AI Score: {candidate['combined_score']} | SL: {stop_loss_price} | TP: {take_profit_price}"
                )

                res = await broker.place_order(req)
                if res.status == OrderStatus.FILLED:
                    # ตั้ง SL/TP ใหม่จากราคาที่ Fill จริง (กันกรณีราคาขยับระหว่างคำนวณกับ Fill)
                    if res.filled_price != price:
                        stop_loss_price, take_profit_price = self.exit_levels(res.filled_price)
                        await broker.update_exit_levels(sym, stop_loss_price, take_profit_price)
                    executed_orders.append(f"BUY {target_qty} {sym} @ {res.filled_price} (SL: {stop_loss_price}, TP: {take_profit_price})")
                    current_holdings.add(sym)
                    cash_available -= target_qty * res.filled_price
                else:
                    rejected_reasons.append(f"{sym}: {res.message}")

        summary = f"ควบคุมความเสี่ยงเรียบร้อย: ส่งคำสั่งสำเร็จ {len(executed_orders)} รายการ"
        if rejected_reasons:
            summary += f" | ปฏิเสธ/ชะลอ {len(rejected_reasons)} รายการเพื่อความปลอดภัย"
        status = "WARNING" if halted_reason else "SUCCESS"

        await db_manager.log_agent(
            agent_name=self.name,
            status=status,
            summary=summary,
            details={"executed": executed_orders, "rejected": rejected_reasons, "daily_loss_pct": round(daily_loss_pct, 2)}
        )

        return AgentExecutionResult(
            agent_name=self.name,
            status=status,
            summary=summary,
            data={"executed_orders": executed_orders, "rejected_reasons": rejected_reasons}
        )
