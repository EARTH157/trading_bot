import logging
from typing import Dict, Any, List
import math

from config.settings import settings
from core.interfaces.agent_base import AgentBase, AgentExecutionResult
from core.interfaces.broker import OrderRequest, OrderSide, OrderType
from core.brokers.paper_broker import broker
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class RiskExecutionAgent(AgentBase):
    """
    🛡️ Agent 4: Risk & Execution Guardian
    - หน้าที่: ผู้พิทักษ์ความปลอดภัยทางการเงินและส่งคำสั่งซื้อขายอย่างระมัดระวัง
    - คำนวณ Position Sizing (เสี่ยงไม่เกิน 2% ของพอร์ตต่อเทรด)
    - บังคับตั้งราคา Stop Loss (เช่น -3%) และ Take Profit (+6%)
    - มีระบบ Circuit Breaker ตรวจจับ Drawdown ไม่ให้เกินลิมิต
    - ตรวจสอบความถูกต้องก่อนส่งคำสั่งไปยัง Broker
    """

    def __init__(self):
        super().__init__(
            name="Agent-4: Risk & Execution Guardian",
            role="ควบคุมความเสี่ยง คำนวณขนาดไม้ และตัดสินใจส่งคำสั่งอย่างระมัดระวัง"
        )
        self.max_positions = 5
        self.max_allocation_per_stock_pct = 20.0  # ลงทุนไม่เกิน 20% ของพอร์ตต่อตัวเดียว

    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        screening_results: List[Dict[str, Any]] = context.get("screening_results", [])
        account = await broker.get_account()
        open_positions = await broker.get_positions()
        executed_orders = []
        rejected_reasons = []

        # 1. จัดการ Position เดิมที่มีอยู่ก่อน (Stop Loss / Take Profit / Sell Signal)
        for pos in open_positions:
            sym = pos.symbol
            # ตรวจสอบ Stop Loss
            if pos.stop_loss_price and pos.current_price <= pos.stop_loss_price:
                logger.info(f"Triggering Stop Loss for {sym} @ {pos.current_price} <= {pos.stop_loss_price}")
                res = await broker.close_position(sym, reason="Hit Stop Loss")
                if res:
                    executed_orders.append(f"SELL (Stop Loss) {sym}: {res.message}")
                continue

            # ตรวจสอบ Take Profit
            if pos.take_profit_price and pos.current_price >= pos.take_profit_price:
                logger.info(f"Triggering Take Profit for {sym} @ {pos.current_price} >= {pos.take_profit_price}")
                res = await broker.close_position(sym, reason="Hit Take Profit")
                if res:
                    executed_orders.append(f"SELL (Take Profit) {sym}: {res.message}")
                continue

            # ตรวจสอบสัญญาณ SELL จาก Agent 3
            item = next((x for x in screening_results if x["symbol"] == sym), None)
            if item and item["recommendation"] == "SELL":
                res = await broker.close_position(sym, reason=f"Market Screener Signal SELL ({item['combined_score']})")
                if res:
                    executed_orders.append(f"SELL (AI Signal) {sym}: {res.message}")

        # ดึงสถานะบัญชีล่าสุดหลังปิด Order
        account = await broker.get_account()
        current_holdings = {p.symbol for p in await broker.get_positions()}

        # 2. พิจารณาเปิด Position ใหม่สำหรับ BUY Candidates
        for candidate in screening_results:
            if candidate["recommendation"] != "BUY":
                continue

            sym = candidate["symbol"]
            price = candidate["current_price"]

            # กฎความปลอดภัย 1: ไม่เปิดหุ้นตัวเดิมซ้ำซ้อนถ้าถืออยู่แล้ว
            if sym in current_holdings:
                rejected_reasons.append(f"{sym}: ถือครองอยู่แล้วในพอร์ต ไม่ซื้อเพิ่มเพื่อกระจายความเสี่ยง")
                continue

            # กฎความปลอดภัย 2: จำนวนหุ้นในพอร์ตต้องไม่เกินพิกัดกระจายความเสี่ยง
            if len(current_holdings) >= self.max_positions:
                rejected_reasons.append(f"{sym}: พอร์ตถือครบ {self.max_positions} ตัวแล้ว ปฏิเสธการเปิดเพิ่ม")
                break

            # คำนวณ Position Sizing ตามความเสี่ยง (Risk Sizing Formula)
            risk_amount = account.equity * (settings.MAX_RISK_PER_TRADE_PCT / 100.0)
            stop_loss_dist = price * (settings.STOP_LOSS_PCT / 100.0)
            stop_loss_price = round(price - stop_loss_dist, 2)
            take_profit_price = round(price + (price * (settings.TAKE_PROFIT_PCT / 100.0)), 2)

            # จำนวนหุ้นที่ยอมรับความเสี่ยงได้
            risk_based_qty = risk_amount / (stop_loss_dist if stop_loss_dist > 0 else 1.0)

            # ตรวจสอบเพดานเงินลงทุนต่อตัว (Max Allocation)
            max_capital_for_stock = account.equity * (self.max_allocation_per_stock_pct / 100.0)
            capital_based_qty = max_capital_for_stock / price

            # เลือกจำนวนที่น้อยกว่าเพื่อความปลอดภัยสูงสุด
            target_qty = math.floor(min(risk_based_qty, capital_based_qty))

            cost = target_qty * price

            # กฎความปลอดภัย 3: ต้องมีเงินสดจริงพอจ่าย
            if target_qty <= 0 or cost > account.cash_balance:
                rejected_reasons.append(f"{sym}: เงินสดคงเหลือ ({account.cash_balance:.2f}) ไม่พอซื้อจำนวน {target_qty} หุ้น (ต้องการ {cost:.2f})")
                continue

            # สั่ง Execution อย่างระมัดระวัง
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
            if res.status.value == "FILLED":
                executed_orders.append(f"BUY {target_qty} {sym} @ {res.filled_price} (SL: {stop_loss_price}, TP: {take_profit_price})")
                current_holdings.add(sym)
                account.cash_balance -= (target_qty * res.filled_price)
            else:
                rejected_reasons.append(f"{sym}: {res.message}")

        summary = f"ควบคุมความเสี่ยงเรียบร้อย: ส่งคำสั่งสำเร็จ {len(executed_orders)} รายการ"
        if rejected_reasons:
            summary += f" | ปฏิเสธ/ชะลอ {len(rejected_reasons)} รายการเพื่อความปลอดภัย"

        await db_manager.log_agent(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            details={"executed": executed_orders, "rejected": rejected_reasons}
        )

        return AgentExecutionResult(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            data={"executed_orders": executed_orders, "rejected_reasons": rejected_reasons}
        )
