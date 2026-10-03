import os
import glob
import time
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
import urllib.parse
import requests
import asyncio

from config.settings import settings
from core.interfaces.agent_base import AgentBase, AgentExecutionResult
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

class NewsScoutAgent(AgentBase):
    """
    🤖 Agent 1: News Scout
    - หน้าที่: รวบรวมข่าวสารการเงินและปัจจัยพื้นฐานของหุ้นใน Watchlist
    - จัดเก็บเป็นไฟล์ Markdown (.md) ชั่วคราวลงใน `data/temp_news/`
    - มีระบบ Auto-cleanup ลบไฟล์ข่าวเก่าที่เกิน 2 วันทิ้งอัตโนมัติ
    """

    def __init__(self):
        super().__init__(
            name="Agent-1: News Scout",
            role="รวบรวมข่าวสารการเงินและแปลงเป็นเอกสาร Markdown ชั่วคราว"
        )
        self.output_dir: Path = settings.TEMP_NEWS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_old_files(self, max_age_hours: int = 48):
        """ลบไฟล์ Markdown เก่าเพื่อประหยัดพื้นที่ดิสก์"""
        now = time.time()
        for fpath in glob.glob(str(self.output_dir / "*.md")):
            try:
                if os.stat(fpath).st_mtime < now - (max_age_hours * 3600):
                    os.remove(fpath)
            except Exception as e:
                logger.debug(f"Error removing old temp file {fpath}: {e}")

    def _fetch_stock_news(self, symbol: str) -> List[Dict[str, str]]:
        """ดึงข่าวล่าสุดของหุ้นผ่าน Yahoo Finance News Feed"""
        articles = []
        try:
            # ใช้วิธีดึง RSS feed ของ Yahoo Finance สำหรับ Ticker นั้นๆ
            rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(symbol)}&region=US&lang=en-US"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(rss_url, headers=headers, timeout=5)

            if resp.status_code == 200 and "<item>" in resp.text:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                for item in root.findall("./channel/item")[:3]:  # เอา 3 ข่าวเด่น
                    title = item.findtext("title") or "No Title"
                    link = item.findtext("link") or ""
                    pub_date = item.findtext("pubDate") or ""
                    description = item.findtext("description") or ""
                    articles.append({
                        "title": title.strip(),
                        "link": link.strip(),
                        "pub_date": pub_date.strip(),
                        "summary": description.strip()
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch live RSS for {symbol}: {e}")

        # ไม่สร้างข่าวจำลอง: ถ้าไม่มีข่าวจริง Agent 2 จะให้ Sentiment เป็น NEUTRAL (ไม่มีข้อมูล)
        return articles

    def _save_to_markdown(self, symbol: str, articles: List[Dict[str, str]]) -> Path:
        """แปลงข่าวเป็น Markdown file"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{timestamp}.md"
        filepath = self.output_dir / filename

        content = [
            f"# รายงานข่าวและข้อมูลวิเคราะห์สำหรับ: {symbol}",
            f"- **รวบรวมเมื่อ**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"- **จำนวนข่าว**: {len(articles)} ข่าว",
            "",
            "## สรุปหัวข้อข่าวล่าสุด (Latest Headlines)",
            ""
        ]

        if not articles:
            content.append("_ไม่พบข่าวล่าสุด (ดึง RSS ไม่สำเร็จหรือไม่มีข่าว)_")

        for idx, art in enumerate(articles, 1):
            content.extend([
                f"### {idx}. {art['title']}",
                f"- **วันที่เผยแพร่**: {art['pub_date']}",
                f"- **ที่มา/ลิงก์**: {art['link']}",
                f"- **เนื้อหาโดยย่อ**: {art['summary']}",
                ""
            ])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        return filepath

    async def run(self, context: Dict[str, Any]) -> AgentExecutionResult:
        """รันกระบวนการรวบรวมข่าวของหุ้นทุกตัวใน Watchlist"""
        self._cleanup_old_files()
        symbols = context.get("symbols", settings.watchlist_symbols)
        created_files: Dict[str, str] = {}
        article_counts: Dict[str, int] = {}

        for symbol in symbols:
            articles = await asyncio.to_thread(self._fetch_stock_news, symbol)
            md_path = self._save_to_markdown(symbol, articles)
            created_files[symbol] = str(md_path)
            article_counts[symbol] = len(articles)

        no_news = [s for s, n in article_counts.items() if n == 0]
        summary = f"รวบรวมข่าวสารสำหรับหุ้น {len(created_files)} ตัวสำเร็จ ({', '.join(symbols)}) บันทึกเป็น .md ชั่วคราวเรียบร้อย"
        if no_news:
            summary += f" | ไม่พบข่าว: {', '.join(no_news)}"

        await db_manager.log_agent(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            details={"files": created_files, "article_counts": article_counts}
        )

        return AgentExecutionResult(
            agent_name=self.name,
            status="SUCCESS",
            summary=summary,
            data={"news_files": created_files, "article_counts": article_counts}
        )
