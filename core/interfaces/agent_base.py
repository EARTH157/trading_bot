from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from pydantic import BaseModel, Field

from config.settings import settings

logger = logging.getLogger(__name__)

class AgentExecutionResult(BaseModel):
    agent_name: str
    status: str  # 'SUCCESS', 'WARNING', 'ERROR'
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class AgentBase(ABC):
    """Abstract Base Class สำหรับ AI Agents ทุกตัวใน Pipeline"""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.gemini_client = None
        self._init_llm()

    def _init_llm(self):
        """กำหนดค่า Gemini LLM (google-genai SDK) หากมี API Key"""
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info(f"[{self.name}] Gemini LLM initialized with model {settings.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to initialize Gemini API: {e}. Fallback to local heuristic.")
                self.gemini_client = None
        else:
            logger.info(f"[{self.name}] No GEMINI_API_KEY provided. Operating in Rule-based / Fallback mode.")

    async def call_llm(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_output: bool = False
    ) -> str:
        """เรียก Gemini LLM แบบ Async หรือคืนค่าว่างกรณีไม่มี Key / เรียกไม่สำเร็จ"""
        if self.gemini_client:
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json" if json_output else None,
                )
                response = await self.gemini_client.aio.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
                return (response.text or "").strip()
            except Exception as e:
                logger.error(f"[{self.name}] Gemini call error: {e}")
                return ""
        return ""

    @abstractmethod
    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        """ฟังก์ชันหลักที่แต่ละ Agent ต้อง Implement"""
        pass
