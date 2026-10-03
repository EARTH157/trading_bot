import asyncio
import logging
import math
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional, Set
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config.settings import settings, BASE_DIR
from core.brokers.paper_broker import broker
from core.data.yahoo_feed import data_feed
from core.agents.pipeline import pipeline
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

# ชื่อไฟล์ข่าวที่ Agent 1 สร้าง: <SYMBOL>_<YYYYMMDD>_<HHMMSS>.md
NEWS_FILENAME_RE = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}_\d{8}_\d{6}\.md$")

def sanitize_json_data(obj: Any) -> Any:
    """แปลง NaN / Inf ให้อยู่ในรูป None เพื่อให้ JSON ไม่พัง"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_json_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_data(v) for v in obj]
    return obj

# WebSocket Connection Manager
class ConnectionManager:
    """จัดการการเชื่อมต่อ WebSocket และกระจายข่าวสาร Real-time (ตัด Connection ที่ตายแล้วออกอัตโนมัติ)"""
    def __init__(self):
        self.active_connections: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    async def send_personal(self, websocket: WebSocket, message: dict) -> bool:
        """ส่งข้อความถึง Client 1 ราย คืน False หากส่งไม่สำเร็จ (Client หลุดไปแล้ว)"""
        lock = self.active_connections.get(websocket)
        if lock is None:
            return False
        try:
            async with lock:
                await websocket.send_json(sanitize_json_data(message))
            return True
        except Exception:
            self.disconnect(websocket)
            return False

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections.keys()):
            await self.send_personal(connection, message)

manager = ConnectionManager()

async def _risk_monitor_loop(interval_seconds: int):
    """ตรวจ Stop Loss / Take Profit เป็นระยะ ไม่ต้องรอผู้ใช้กดรัน Pipeline"""
    agent4 = pipeline.agent4
    while True:
        await asyncio.sleep(interval_seconds)
        if pipeline.is_running:
            continue  # Pipeline ตรวจ SL/TP เองอยู่แล้วในรอบนั้น
        try:
            # ตั้ง Equity ต้นวันของ Circuit Breaker ให้เร็วที่สุด แม้ยังไม่มีการรัน Pipeline ในวันนั้น
            await broker.get_daily_loss_pct()
            executed = await agent4.enforce_exits()
            if executed:
                summary = f"Risk Monitor ปิด Position อัตโนมัติ {len(executed)} รายการ"
                await db_manager.log_agent(agent4.name, "SUCCESS", summary, {"executed": executed})
                await manager.broadcast({
                    "type": "RISK_EXIT",
                    "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
                    "message": f"🛡️ {summary}: {'; '.join(executed)}"
                })
        except Exception:
            logger.exception("Risk monitor iteration failed")

async def _pipeline_scheduler_loop(interval_minutes: int):
    """รัน 4-Agent Pipeline อัตโนมัติตามรอบเวลา"""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await pipeline.execute_cycle()
        except Exception:
            logger.exception("Scheduled pipeline run failed")

_background_tasks: Set[asyncio.Task] = set()

def _spawn(coro) -> asyncio.Task:
    """สร้าง Background Task พร้อมเก็บ Reference ไว้ (กัน Task ถูก Garbage Collect)"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.init_db()
    await broker.load_state()
    await broker.get_daily_loss_pct()
    # เชื่อมต่อ Real-time event ของ AI Pipeline ไปยัง WebSocket
    pipeline.add_listener(manager.broadcast)

    loops = []
    if settings.RISK_CHECK_INTERVAL_SECONDS > 0:
        loops.append(_spawn(_risk_monitor_loop(settings.RISK_CHECK_INTERVAL_SECONDS)))
    if settings.PIPELINE_INTERVAL_MINUTES > 0:
        loops.append(_spawn(_pipeline_scheduler_loop(settings.PIPELINE_INTERVAL_MINUTES)))
    logger.info(
        "Trading Bot Dashboard started (risk monitor: %ss, pipeline schedule: %s)",
        settings.RISK_CHECK_INTERVAL_SECONDS or "off",
        f"{settings.PIPELINE_INTERVAL_MINUTES}m" if settings.PIPELINE_INTERVAL_MINUTES > 0 else "manual only",
    )
    try:
        yield
    finally:
        for task in list(_background_tasks):
            task.cancel()
        await asyncio.gather(*_background_tasks, return_exceptions=True)

app = FastAPI(title="AI Stock Trading Bot Dashboard", version="1.0.0", lifespan=lifespan)

# ป้องกัน DNS Rebinding: รับเฉพาะ Host ที่อนุญาต
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

def _is_cross_origin(origin: Optional[str], host: Optional[str]) -> bool:
    """True หาก Origin ของ Browser ไม่ตรงกับ Host ของ Dashboard (เช่น เว็บอื่นพยายามยิงคำสั่ง)"""
    if not origin:
        return False  # ไม่ใช่คำขอจาก Browser ข้ามเว็บ (เช่น curl)
    return urlsplit(origin).netloc.lower() != (host or "").lower()

@app.middleware("http")
async def block_cross_site_requests(request: Request, call_next):
    """ป้องกัน CSRF: เว็บอื่นห้ามสั่ง POST (เช่น Sell All) มาที่ Dashboard"""
    if request.method not in ("GET", "HEAD", "OPTIONS") and _is_cross_origin(
        request.headers.get("origin"), request.headers.get("host")
    ):
        return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
    return await call_next(request)

# Setup Templates directory
TEMPLATES_DIR = BASE_DIR / "dashboard" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """ส่งหน้า Dashboard HTML"""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "watchlist": settings.watchlist_symbols,
            "app_mode": settings.APP_MODE,
            "gemini_model": settings.GEMINI_MODEL,
            "has_gemini_key": bool(settings.GEMINI_API_KEY)
        }
    )

@app.get("/api/status")
async def get_system_status():
    """ดึงข้อมูลสถานะพอร์ตและบอททั้งหมด"""
    account = await broker.get_account()
    positions = list(broker.positions.values())
    orders = await db_manager.get_recent_orders(limit=20)
    logs = await db_manager.get_recent_agent_logs(limit=15)

    return sanitize_json_data({
        "account": account.model_dump(),
        "positions": [p.model_dump() for p in positions],
        "orders": orders,
        "agent_logs": logs,
        "pipeline": {
            "is_running": pipeline.is_running,
            "current_agent": pipeline.current_running_agent,
            "last_run": pipeline.last_run_time,
            "latest_result": pipeline.latest_pipeline_result
        },
        "watchlist": settings.watchlist_symbols
    })

@app.post("/api/pipeline/run")
async def trigger_pipeline_run():
    """สั่งรัน 4 AI Agents Pipeline 1 รอบวัฏจักร"""
    if pipeline.is_running:
        return JSONResponse(
            status_code=400,
            content={"message": "กระบวนการวิเคราะห์กำลังทำงานอยู่ กรุณารอสักครู่"}
        )

    # รัน async background
    _spawn(pipeline.execute_cycle())
    return {"status": "STARTED", "message": "เริ่มกระบวนการ 4 AI Agents Pipeline สำเร็จ"}

@app.post("/api/emergency/sell_all")
async def emergency_sell_all():
    """Panic Button: หยุดการเปิด Position ใหม่ของรอบที่กำลังทำงาน และขายหุ้นทุกตัวในพอร์ตทันที"""
    pipeline.request_stop()
    orders = await broker.close_all_positions(reason="Panic Button: Emergency Sell All")
    return {
        "status": "SUCCESS",
        "message": f"สั่งปิด Position ทั้งหมดสำเร็จ ({len(orders)} รายการ)",
        "orders": [o.model_dump() for o in orders]
    }

@app.post("/api/positions/close/{symbol}")
async def close_single_position(symbol: str):
    """ปิด Position หุ้นรายตัว"""
    res = await broker.close_position(symbol.upper(), reason="Manual Close from Dashboard")
    if not res:
        raise HTTPException(status_code=404, detail="ไม่พบ Position นี้ในพอร์ต")
    return {"status": "SUCCESS", "order": res.model_dump()}

@app.get("/api/chart/{symbol}")
async def get_chart_data(symbol: str):
    """ดึงข้อมูลแท่งเทียนสำหรับ TradingView Lightweight Chart"""
    df = await data_feed.get_historical_data(symbol.upper(), timeframe="1d", period="6mo")
    if df.empty:
        return {"data": []}

    def _num(value: Any) -> Optional[float]:
        value = float(value)
        return None if math.isnan(value) else round(value, 2)

    candles = []
    for idx, row in df.iterrows():
        # Lightweight Charts format: {time: 'YYYY-MM-DD', open: 0, high: 0, low: 0, close: 0}
        candles.append({
            "time": idx.strftime("%Y-%m-%d"),
            "open": _num(row["open"]),
            "high": _num(row["high"]),
            "low": _num(row["low"]),
            "close": _num(row["close"]),
            "volume": int(row.get("volume", 0)),
            "ema20": _num(row["ema20"]),
            "ema50": _num(row["ema50"]),
        })
    return {"symbol": symbol.upper(), "synthetic": bool(df.attrs.get("synthetic")), "data": candles}

@app.get("/api/news_files")
async def get_temp_news_files():
    """ดึงรายการไฟล์ข่าว Markdown ชั่วคราวที่ Agent 1 สร้างไว้"""
    news_dir = settings.TEMP_NEWS_DIR
    files = []
    if news_dir.exists():
        for p in sorted(news_dir.glob("*.md"), reverse=True):
            files.append({
                "filename": p.name,
                "size_kb": round(p.stat().st_size / 1024, 2),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return {"files": files}

@app.get("/api/news_file/{filename}")
async def read_temp_news_file(filename: str):
    """อ่านเนื้อหาไฟล์ข่าว Markdown ชั่วคราว (เฉพาะไฟล์ในโฟลเดอร์ข่าวเท่านั้น)"""
    if not NEWS_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    news_dir = settings.TEMP_NEWS_DIR.resolve()
    file_path = (news_dir / filename).resolve()
    if file_path.parent != news_dir or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    content = file_path.read_text(encoding="utf-8")
    return {"filename": filename, "content": content}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if _is_cross_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            # ส่ง heartbeat / status ทุกๆ 2 วินาที
            account = await broker.get_account()
            sent = await manager.send_personal(websocket, {
                "type": "TICK",
                "cash": account.cash_balance,
                "equity": account.equity,
                "unrealized_pnl": account.unrealized_pnl,
                "realized_pnl": account.realized_pnl,
                "positions_count": len(broker.positions),
                "pipeline_running": pipeline.is_running,
                "last_run": pipeline.last_run_time
            })
            if not sent:
                break
            # รอข้อความจาก Client ไม่เกิน 2 วินาที: ทำให้รู้ทันทีเมื่อ Client ปิดการเชื่อมต่อ
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket loop error")
    finally:
        manager.disconnect(websocket)
