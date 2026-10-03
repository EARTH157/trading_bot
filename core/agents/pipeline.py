import asyncio
import logging
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime

from core.agents.news_scout import NewsScoutAgent
from core.agents.sentiment_analyst import SentimentAnalystAgent
from core.agents.market_screener import MarketScreenerAgent
from core.agents.risk_guardian import RiskExecutionAgent
from core.brokers.paper_broker import broker
from config.settings import settings

logger = logging.getLogger(__name__)

class TradingPipeline:
    """
    Orchestrator เชื่อมโยงการทำงานของทั้ง 4 AI Agents พร้อมระบบ Real-time Event Broadcaster
    """

    def __init__(self):
        self.agent1 = NewsScoutAgent()
        self.agent2 = SentimentAnalystAgent()
        self.agent3 = MarketScreenerAgent()
        self.agent4 = RiskExecutionAgent()
        self.is_running = False
        self.current_running_agent: Optional[int] = None
        self.last_run_time: str = "ยังไม่ได้เริ่มรอบการวิเคราะห์"
        self.latest_pipeline_result: Dict[str, Any] = {}
        self.listeners: List[Callable] = []
        # ตั้งค่าเมื่อผู้ใช้กด Panic Button: Agent 4 จะไม่เปิด Position ใหม่ในรอบที่กำลังทำงาน
        self.stop_event = asyncio.Event()

    def request_stop(self):
        """ขอให้รอบที่กำลังทำงานหยุดเปิด Position ใหม่ (มีผลจนกว่าจะเริ่มรอบถัดไป)"""
        if self.is_running:
            self.stop_event.set()

    def add_listener(self, callback: Callable):
        """เพิ่มฟังก์ชันสำหรับรับ Real-time Events (เช่น WebSocket Broadcaster)"""
        if callback not in self.listeners:
            self.listeners.append(callback)

    async def emit_event(self, event_type: str, payload: Dict[str, Any]):
        """กระจาย Event แบบ Real-time ไปยังทุก Listener"""
        event_data = {
            "type": event_type,
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            **payload
        }
        for listener in self.listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event_data)
                else:
                    listener(event_data)
            except Exception as e:
                logger.error(f"Error broadcasting event: {e}")

    async def execute_cycle(self) -> Dict[str, Any]:
        """รันครบ 1 รอบวัฏจักรของ 4 Agents พร้อมส่งสถานะ Real-time Animation"""
        if self.is_running:
            logger.warning("Pipeline is already executing a cycle. Skipping duplicate call.")
            return {"status": "ALREADY_RUNNING", "message": "รอบการวิเคราะห์กำลังดำเนินการอยู่"}

        self.is_running = True
        self.stop_event.clear()
        start_time = datetime.utcnow()
        cycle_result = {"started_at": start_time.strftime("%Y-%m-%d %H:%M:%S UTC"), "steps": []}

        try:
            await self.emit_event("PIPELINE_START", {
                "message": "🚀 เริ่มต้นรอบการทำงาน 4-Agent Autonomous Pipeline...",
                "active_agent": 1
            })
            await asyncio.sleep(0.5)

            # ----------------------------------------------------
            # Step 1: Agent 1 - News Scout
            # ----------------------------------------------------
            self.current_running_agent = 1
            await self.emit_event("AGENT_STATE", {
                "agent_id": 1,
                "status": "RUNNING",
                "thought": f"กำลังสแกน RSS และดึงข่าวสารล่าสุดของ {', '.join(settings.watchlist_symbols)}..."
            })
            await asyncio.sleep(0.8)

            res1 = await self.agent1.run({})
            cycle_result["steps"].append(res1.model_dump())

            await self.emit_event("AGENT_STATE", {
                "agent_id": 1,
                "status": "COMPLETED",
                "thought": f"บันทึกไฟล์ข่าว .md ชั่วคราวเรียบร้อย {len(res1.data.get('news_files', {}))} ไฟล์",
                "summary": res1.summary,
                "data": res1.data
            })
            await asyncio.sleep(0.6)

            # Data Beam: Agent 1 -> Agent 2
            await self.emit_event("DATA_TRANSFER", {
                "from_agent": 1,
                "to_agent": 2,
                "message": "⚡ ส่งมอบไฟล์ข่าว Markdown ไปยัง Agent 2 (Sentiment Analyst)..."
            })
            await asyncio.sleep(0.8)

            # ----------------------------------------------------
            # Step 2: Agent 2 - Sentiment Analyst (Gemini)
            # ----------------------------------------------------
            self.current_running_agent = 2
            await self.emit_event("AGENT_STATE", {
                "agent_id": 2,
                "status": "RUNNING",
                "thought": (
                    f"กำลังเชื่อมต่อ Google Gemini ({settings.GEMINI_MODEL}) เพื่อวิเคราะห์ Sentiment และสกัด Catalysts/Risks..."
                    if self.agent2.gemini_client else
                    "ไม่มี GEMINI_API_KEY: วิเคราะห์ Sentiment ด้วย Heuristic Engine..."
                )
            })
            await asyncio.sleep(0.8)

            res2 = await self.agent2.run(res1.data)
            cycle_result["steps"].append(res2.model_dump())

            await self.emit_event("AGENT_STATE", {
                "agent_id": 2,
                "status": "COMPLETED",
                "thought": "สกัดคะแนน Sentiment สำเร็จ ส่งต่อทิศทางเชิงบวก/ลบ",
                "summary": res2.summary,
                "data": res2.data
            })
            await asyncio.sleep(0.6)

            # Data Beam: Agent 2 -> Agent 3
            await self.emit_event("DATA_TRANSFER", {
                "from_agent": 2,
                "to_agent": 3,
                "message": "⚡ ส่งต่อคะแนน Sentiment ไปยัง Agent 3 (Market Screener)..."
            })
            await asyncio.sleep(0.8)

            # ----------------------------------------------------
            # Step 3: Agent 3 - Market Screener
            # ----------------------------------------------------
            self.current_running_agent = 3
            await self.emit_event("AGENT_STATE", {
                "agent_id": 3,
                "status": "RUNNING",
                "thought": "กำลังดึงราคาแท่งเทียน คำนวณ EMA 20/50, RSI 14 และ ATR ผสานกับ Sentiment..."
            })
            await asyncio.sleep(0.8)

            res3 = await self.agent3.run(res2.data)
            cycle_result["steps"].append(res3.model_dump())

            await self.emit_event("AGENT_STATE", {
                "agent_id": 3,
                "status": "COMPLETED",
                "thought": f"คัดกรองหุ้นเสร็จสิ้น พบหุ้นน่าซื้อ: {', '.join(res3.data.get('buy_candidates', [])) or 'ไม่มี'}",
                "summary": res3.summary,
                "data": res3.data
            })
            await asyncio.sleep(0.6)

            # Data Beam: Agent 3 -> Agent 4
            await self.emit_event("DATA_TRANSFER", {
                "from_agent": 3,
                "to_agent": 4,
                "message": "⚡ ส่งมอบรายชื่อหุ้นเป้าหมายไปยัง Agent 4 (Risk Guardian)..."
            })
            await asyncio.sleep(0.8)

            # ----------------------------------------------------
            # Step 4: Agent 4 - Risk Guardian
            # ----------------------------------------------------
            self.current_running_agent = 4
            await self.emit_event("AGENT_STATE", {
                "agent_id": 4,
                "status": "RUNNING",
                "thought": "ผู้พิทักษ์ความเสี่ยง: ตรวจสอบ Stop Loss เดิม, คำนวณ Position Sizing (Risk 2%), เช็คเงินสด..."
            })
            await asyncio.sleep(0.8)

            res4 = await self.agent4.run({**res3.data, "stop_event": self.stop_event})
            cycle_result["steps"].append(res4.model_dump())

            await self.emit_event("AGENT_STATE", {
                "agent_id": 4,
                "status": "COMPLETED",
                "thought": f"ควบคุมความเสี่ยงและส่งออเดอร์เรียบร้อย ({len(res4.data.get('executed_orders', []))} คำสั่ง)",
                "summary": res4.summary,
                "data": res4.data
            })
            await asyncio.sleep(0.6)

            await broker.record_snapshot()

            cycle_result["status"] = "SUCCESS"
            cycle_result["completed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            self.last_run_time = datetime.utcnow().strftime("%H:%M:%S")
            self.latest_pipeline_result = cycle_result

            await self.emit_event("PIPELINE_COMPLETE", {
                "message": "✨ สิ้นสุดรอบการวิเคราะห์ 4-Agent Pipeline พอร์ตได้รับการอัปเดตเรียบร้อย!",
                "result": cycle_result
            })

        except Exception as e:
            logger.exception(f"Error executing AI Pipeline: {e}")
            cycle_result["status"] = "ERROR"
            cycle_result["error"] = str(e)
            await self.emit_event("PIPELINE_ERROR", {
                "message": f"❌ เกิดข้อผิดพลาดในการรัน Pipeline: {e}"
            })
        finally:
            self.current_running_agent = None
            self.is_running = False

        return cycle_result

pipeline = TradingPipeline()
