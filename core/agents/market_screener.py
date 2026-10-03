import logging
from typing import Dict, Any, List

from config.settings import settings
from core.interfaces.agent_base import AgentBase, AgentExecutionResult
from core.data.yahoo_feed import data_feed
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class MarketScreenerAgent(AgentBase):
    """
    📊 Agent 3: Market Screener
    - หน้าที่: วิเคราะห์ทิศทางตลาด คัดกรองหุ้นน่าลงทุน (Market Screener)
    - ผสานปัจจัยเชิงเทคนิค (EMA 20/50, RSI 14) ร่วมกับคะแนน Sentiment ข่าวจาก Agent 2
    - คัดเลือกหุ้นที่มีแต้มต่อสูง (High Probability Setup) ส่งต่อให้ Agent 4
    """

    def __init__(self):
        super().__init__(
            name="Agent-3: Market Screener",
            role="คัดกรองหุ้นที่มีสัญญาณบวกทั้งกราฟเทคนิคและข่าวสาร ส่งต่อเป้าหมายเข้าพอร์ต"
        )

    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        sentiment_analysis: Dict[str, Any] = context.get("sentiment_analysis", {})
        # คัดกรองเฉพาะหุ้นใน Watchlist ที่ตั้งค่าไว้เท่านั้น (ไม่ใช้ Key จากผลลัพธ์ LLM เป็นตัวกำหนดจักรวาลหุ้น)
        symbols = settings.watchlist_symbols
        screening_results: List[Dict[str, Any]] = []
        skipped: List[str] = []

        for symbol in symbols:
            # 6 เดือน (~125 แท่ง) เพื่อให้ EMA50 มีข้อมูลอุ่นเครื่องเพียงพอ
            df = await data_feed.get_historical_data(symbol, timeframe="1d", period="6mo")
            if df.empty or len(df) < 50:
                skipped.append(f"{symbol}: ข้อมูลราคาไม่พอ ({len(df)} แท่ง)")
                continue
            if df.attrs.get("synthetic") and not settings.ALLOW_SYNTHETIC_TRADING:
                skipped.append(f"{symbol}: ไม่มีข้อมูลราคาจริง (ข้ามการคัดกรอง)")
                continue

            latest_close = float(df["close"].iloc[-1])
            ema20 = float(df["ema20"].iloc[-1])
            ema50 = float(df["ema50"].iloc[-1])
            rsi = float(df["rsi"].iloc[-1]) if "rsi" in df else 50.0
            atr = float(df["atr"].iloc[-1]) if "atr" in df else (latest_close * 0.02)

            sent = sentiment_analysis.get(symbol, {"score": 0.0, "label": "NEUTRAL"})
            sent_score = sent.get("score", 0.0)

            # ให้คะแนนเชิงเทคนิค (Technical Score)
            tech_score = 0.0
            signals = []

            # 1. เทรนด์ EMA: ขาขึ้นถ้า EMA20 > EMA50
            if ema20 > ema50:
                tech_score += 0.4
                signals.append("EMA ขาขึ้น (EMA20 > EMA50)")
            else:
                tech_score -= 0.3
                signals.append("EMA ขาลง (EMA20 < EMA50)")

            # 2. RSI Condition: ไม่เข้าข่าย Overbought (>70)
            if 40 <= rsi <= 65:
                tech_score += 0.3
                signals.append(f"RSI แข็งแกร่ง ({rsi:.1f})")
            elif rsi < 35:
                tech_score += 0.2
                signals.append(f"RSI Oversold เหมาะกับการสะสม ({rsi:.1f})")
            elif rsi > 70:
                tech_score -= 0.4
                signals.append(f"RSI Overbought เริ่มตึงตัว ({rsi:.1f})")

            # ผสาน Sentiment จาก Agent 2
            combined_score = (tech_score * 0.6) + (sent_score * 0.4)

            # สรุป Recommendation
            if combined_score > 0.25:
                recommendation = "BUY"
            elif combined_score < -0.2:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"

            screening_results.append({
                "symbol": symbol,
                "current_price": round(latest_close, 2),
                "ema20": round(ema20, 2),
                "ema50": round(ema50, 2),
                "rsi": round(rsi, 1),
                "atr": round(atr, 2),
                "sentiment_label": sent.get("label", "NEUTRAL"),
                "sentiment_score": sent_score,
                "combined_score": round(combined_score, 2),
                "recommendation": recommendation,
                "reasons": signals
            })

        # เรียงลำดับจากคะแนนสูงสุดไปต่ำสุด
        screening_results.sort(key=lambda x: x["combined_score"], reverse=True)

        buy_candidates = [r["symbol"] for r in screening_results if r["recommendation"] == "BUY"]
        summary = f"คัดกรองเสร็จสิ้น: พบหุ้นน่าสนใจสำหรับพอร์ต (BUY) {len(buy_candidates)} ตัว: {', '.join(buy_candidates) if buy_candidates else 'ไม่มี (รอจังหวะ)'}"
        if skipped:
            summary += f" | ข้าม {len(skipped)} ตัว (ไม่มีข้อมูลราคาจริง)"
        status = "WARNING" if skipped else "SUCCESS"

        await db_manager.log_agent(
            agent_name=self.name,
            status=status,
            summary=summary,
            details={"candidates": screening_results, "skipped": skipped}
        )

        return AgentExecutionResult(
            agent_name=self.name,
            status=status,
            summary=summary,
            data={"screening_results": screening_results, "buy_candidates": buy_candidates}
        )
