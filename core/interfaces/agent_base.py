import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from abc import ABC, abstractmethod
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import json
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
        """กำหนดค่า Gemini LLM หากมี API Key"""
        if settings.GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self.gemini_client = genai.GenerativeModel(settings.GEMINI_MODEL)
                logger.info(f"[{self.name}] Gemini LLM initialized with model {settings.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to initialize Gemini API: {e}. Fallback to local heuristic.")
                self.gemini_client = None
        else:
            logger.info(f"[{self.name}] No GEMINI_API_KEY provided. Operating in Rule-based / Fallback mode.")

    async def call_llm(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """เรียก Gemini LLM หรือส่งคำตอบจำลองกรณีไม่มี Key แบบ Non-blocking"""
        if self.gemini_client:
            try:
                full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
                response = await asyncio.to_thread(self.gemini_client.generate_content, full_prompt)
                return response.text.strip()
            except Exception as e:
                logger.error(f"[{self.name}] Gemini call error: {e}")
                return ""
        return ""

    @abstractmethod
    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        """ฟังก์ชันหลักที่แต่ละ Agent ต้อง Implement"""
        pass
