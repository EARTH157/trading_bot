import asyncio
import logging
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn

from config.settings import settings, BASE_DIR
from core.brokers.paper_broker import broker
from core.data.yahoo_feed import data_feed
from core.agents.pipeline import pipeline
from database.db_manager import db_manager

logger = logging.getLogger(__name__)

def sanitize_json_data(obj: Any) -> Any:
    """แปลง NaN / Inf ให้อยู่ในรูป None หรือ 0.0 เพื่อให้ JSON ไม่พัง"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_json_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_data(v) for v in obj]
    return obj

app = FastAPI(title="AI Stock Trading Bot Dashboard", version="1.0.0")

# Setup Templates & Static directories
TEMPLATES_DIR = BASE_DIR / "dashboard" / "templates"
STATIC_DIR = BASE_DIR / "dashboard" / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# WebSocket Connection Manager
class ConnectionManager:
    """จัดการการเชื่อมต่อ WebSocket และกระจายข่าวสาร Real-time อย่างปลอดภัยแบบ Thread-safe"""
    def __init__(self):
        self.active_connections: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    async def send_personal(self, websocket: WebSocket, message: dict):
        lock = self.active_connections.get(websocket)
        if lock:
            try:
                async with lock:
                    await websocket.send_json(message)
            except Exception:
                pass

    async def broadcast(self, message: dict):
        for connection, lock in list(self.active_connections.items()):
            try:
                async with lock:
                    await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    await db_manager.init_db()
    # เชื่อมต่อ Real-time event ของ AI Pipeline ไปยัง WebSocket
    pipeline.add_listener(manager.broadcast)
    # ดึง account ครั้งแรกเพื่อเตรียม snapshot
    await broker.get_account()
    logger.info("Trading Bot Dashboard backend started with real-time AI broadcaster.")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """ส่งหน้า Dashboard HTML"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
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
    positions = await broker.get_positions()
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
    asyncio.create_task(pipeline.execute_cycle())
    return {"status": "STARTED", "message": "เริ่มกระบวนการ 4 AI Agents Pipeline สำเร็จ"}

@app.post("/api/emergency/sell_all")
async def emergency_sell_all():
    """Panic Button: ขายหุ้นทุกตัวในพอร์ตทันที"""
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
    df = await data_feed.get_historical_data(symbol.upper(), timeframe="1d", period="3mo")
    if df.empty:
        return {"data": []}

    candles = []
    for idx, row in df.iterrows():
        # Lightweight Charts format: {time: 'YYYY-MM-DD', open: 0, high: 0, low: 0, close: 0}
        date_str = idx.strftime("%Y-%m-%d")
        candles.append({
            "time": date_str,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row.get("volume", 0)),
            "ema20": round(float(row["ema20"]), 2) if "ema20" in row and not row["ema20"] != row["ema20"] else None,
            "ema50": round(float(row["ema50"]), 2) if "ema50" in row and not row["ema50"] != row["ema50"] else None,
        })
    return {"symbol": symbol.upper(), "data": candles}

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
    """อ่านเนื้อหาไฟล์ข่าว Markdown ชั่วคราว"""
    file_path = settings.TEMP_NEWS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": filename, "content": content}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # ส่ง heartbeat / status ทุกๆ 2 วินาที อย่างปลอดภัย
            account = await broker.get_account()
            positions = await broker.get_positions()
            await manager.send_personal(websocket, {
                "type": "TICK",
                "cash": account.cash_balance,
                "equity": account.equity,
                "unrealized_pnl": account.unrealized_pnl,
                "realized_pnl": account.realized_pnl,
                "positions_count": len(positions),
                "pipeline_running": pipeline.is_running,
                "last_run": pipeline.last_run_time
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
