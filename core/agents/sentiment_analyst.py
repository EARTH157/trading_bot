import re
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

from config.settings import settings
from core.interfaces.agent_base import AgentBase, AgentExecutionResult
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class SentimentAnalystAgent(AgentBase):
    """
    🧠 Agent 2: Sentiment Analyst
    - หน้าที่: อ่านไฟล์ Markdown ข่าวสารจาก Agent 1
    - ใช้ Gemini LLM วิเคราะห์ความรู้สึกเชิงบวก/ลบ (Sentiment Score) และประเมินทิศทางข่าว
    - มีระบบ Batch Processing: ส่งวิเคราะห์หุ้นทุกตัวในคำขอเดียวเพื่อประหยัด Quota และป้องกัน Rate Limit (429)
    - มีระบบ Rule-based Heuristic สลับทำงานอัตโนมัติหากไม่มี API Key หรือติด Limit
    """

    def __init__(self):
        super().__init__(
            name="Agent-2: Sentiment Analyst",
            role="วิเคราะห์เนื้อหาข่าว ประเมิน Sentiment Score และจัดกลุ่มโอกาส/ความเสี่ยง"
        )

    def _heuristic_sentiment(self, text: str) -> Dict[str, Any]:
        """วิเคราะห์แบบ Heuristic ด้วยคีย์เวิร์ดทางการเงิน (กรณีไม่ใช้ API Key หรือติด Rate Limit)"""
        pos_words = ["surge", "gain", "profit", "beat", "growth", "upgrade", "bullish", "record", "jump", "demand", "expand", "soar"]
        neg_words = ["drop", "fall", "loss", "miss", "decline", "downgrade", "bearish", "plunge", "risk", "lawsuit", "slump", "investigation"]

        lower = text.lower()
        pos_count = sum(len(re.findall(rf"\b{w}\b", lower)) for w in pos_words)
        neg_count = sum(len(re.findall(rf"\b{w}\b", lower)) for w in neg_words)

        diff = pos_count - neg_count
        score = max(min(diff * 0.25, 1.0), -1.0)

        if score > 0.15:
            label = "BULLISH"
        elif score < -0.15:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "score": round(score, 2),
            "label": label,
            "catalysts": ["ผลประกอบการและแนวโน้มอุตสาหกรรมทรงตัว"] if label != "BEARISH" else [],
            "risks": ["ความผันผวนของตลาดภาพรวม"] if label != "BULLISH" else [],
            "summary": f"ประเมินสภาวะข่าวภาพรวมอยู่ในเกณฑ์ {label}"
        }

    async def _batch_analyze_with_gemini(self, news_data: Dict[str, str]) -> Dict[str, Any]:
        """ส่งข่าวของหุ้นทุกตัวไปวิเคราะห์พร้อมกันใน 1 Prompt (Single-shot Batching ประหยัด Quota 80%)"""
        news_blocks = []
        for symbol, content in news_data.items():
            # ตัดเนื้อหาไม่ให้ยาวเกินไป
            snippet = content[:1500].strip()
            news_blocks.append(f"### SYMBOL: {symbol}\n{snippet}\n")

        full_news_text = "\n---\n".join(news_blocks)

        prompt = f"""
คุณคือนักวิเคราะห์ Sentiment ตลาดหุ้นระดับมืออาชีพ
กรุณาอ่านข้อมูลข่าวสารของหุ้นต่อไปนี้ แล้ววิเคราะห์ประเด็นเชิงบวก/เชิงลบสำหรับแต่ละตัว:

{full_news_text}

กรุณาตอบกลับเป็น JSON object โดยใช้ Symbol ของหุ้นเป็น Key รูปแบบดังนี้เท่านั้น (ห้ามใส่คำบรรยายอื่นนอกเหนือจาก JSON):
{{
  "AAPL": {{
    "score": 0.35,
    "label": "BULLISH",
    "catalysts": ["ยอดขายอุปกรณ์ทรงตัว", "การลงทุนด้าน AI"],
    "risks": ["การแข่งขันในตลาดสูง"],
    "summary": "ข่าวภาพรวมเป็นบวก มีแรงหนุนจากการพัฒนา AI"
  }},
  ... (สำหรับหุ้นทุกตัวที่ระบุข้างต้น)
}}
"""
        response_text = await self.call_llm(prompt)
        if response_text:
            try:
                # ดึง JSON block ออกมาจาก Markdown
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if isinstance(parsed, dict) and len(parsed) > 0:
                        return parsed
            except Exception as e:
                logger.warning(f"Error parsing Gemini batch JSON: {e}")
        return {}

    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        news_files: Dict[str, str] = context.get("news_files", {})
        news_data: Dict[str, str] = {}

        for symbol, fpath in news_files.items():
            if Path(fpath).exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    news_data[symbol] = f.read()

        # ลองวิเคราะห์แบบ Batch 1 ครั้ง
        results: Dict[str, Any] = {}
        if self.gemini_client and news_data:
            logger.info("Sending batch news analysis to Gemini LLM (1 API call)...")
            batch_result = await self._batch_analyze_with_gemini(news_data)
            results = batch_result

        # สำหรับหุ้นตัวไหนที่ LLM พลาดหรือไม่ตอบ ให้ใช้ Heuristic เสริมทันที
        for symbol, content in news_data.items():
            if symbol not in results or "score" not in results[symbol]:
                results[symbol] = self._heuristic_sentiment(content)

        bullish_count = sum(1 for r in results.values() if r.get("label") == "BULLISH")
        bearish_count = sum(1 for r in results.values() if r.get("label") == "BEARISH")
        summary = f"วิเคราะห์ข่าวสำเร็จ: Bullish {bullish_count} ตัว, Bearish {bearish_count} ตัว, Neutral {len(results) - bullish_count - bearish_count} ตัว"

        await db_manager.log_agent(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            details=results
        )

        return AgentExecutionResult(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            data={"sentiment_analysis": results}
        )
