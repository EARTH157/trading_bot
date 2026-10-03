# 🚀 AI Multi-Agent Stock Trading Bot & Web Dashboard

ระบบเทรดหุ้นอัตโนมัติด้วยสถาปัตยกรรม **4 Autonomous AI Agents** ทำงานร่วมกันแบบ Real-time พร้อม **Web Dashboard** มอนิเตอร์พอร์ตและกระบวนการคิดของ AI วินาทีต่อวินาที

---

## 🌟 ฟีเจอร์หลัก (Core Features)

- **4 Autonomous AI Collaborative Pipeline**:
  1. 🤖 **Agent 1 (News Scout)**: สแกนข่าวการเงินล่าสุดและ RSS Feed บันทึกเป็นเอกสาร Markdown ชั่วคราว
  2. 🧠 **Agent 2 (Sentiment Analyst)**: วิเคราะห์แนวโน้มข่าวด้วย **Google Gemini** (ค่าเริ่มต้น `gemini-2.5-flash`) สกัดปัจจัยบวก (Catalysts) และความเสี่ยง (Risks) — ผลลัพธ์ของ LLM ถูกตรวจสอบ (score ต้องอยู่ในช่วง -1..1 และรับเฉพาะหุ้นใน Watchlist)
  3. 📊 **Agent 3 (Market Screener)**: คำนวณอินดิเคเตอร์ทางเทคนิค (EMA 20/50, RSI 14, ATR) ผสานคะแนน Sentiment เพื่อจัดอันดับหุ้นใน Watchlist
  4. 🛡️ **Agent 4 (Risk Guardian)**: ผู้พิทักษ์ความเสี่ยง คำนวณ Position Sizing, บังคับตั้งราคา Stop Loss (3%) และ Take Profit (6%) จากราคาที่ซื้อได้จริง และมี Circuit Breaker ขาดทุนรายวัน
- **Live AI Cognitive Stream**: กล่องคอนโซลเรดาร์แสดงกระบวนการคิดและข้อความตัดสินใจของ AI สดๆ
- **Real-Time Visual State Animations**: การ์ด AI ขยับแบบ Neon Glow Pulse เมื่อกำลังคิด และเปลี่ยนเป็นสีเขียว Done เมื่อวิเคราะห์เสร็จ
- **TradingView Lightweight Charts**: กราฟแท่งเทียนราคาหุ้นพร้อมเส้นค่าเฉลี่ย EMA 20 และ EMA 50
- **Paper Trading First**: ปลอดภัยด้วยระบบจำลองการเทรด (Virtual Balance $100,000 USD) — สถานะพอร์ตบันทึกลง SQLite และโหลดกลับเมื่อรีสตาร์ท
- **Risk Monitor อัตโนมัติ**: ตรวจ Stop Loss / Take Profit ทุก `RISK_CHECK_INTERVAL_SECONDS` วินาที แม้ไม่ได้กดรัน Pipeline
- **Panic Button**: ปุ่ม Sell All ปิดทุกสถานะในพอร์ตทันที และหยุดการเปิด Position ใหม่ของรอบที่กำลังทำงาน

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, SQLAlchemy (async), aiosqlite
- **AI / LLM**: Google Gemini ผ่าน `google-genai` SDK
- **Market Data**: Yahoo Finance (yfinance)
- **Database**: SQLite
- **Frontend**: Tailwind CSS, TradingView Lightweight Charts v4, Lucide Icons, WebSocket Real-time Broadcasting

---

## 🚀 วิธีติดตั้งและเริ่มต้นใช้งาน (Quickstart)

### 1. โคลน Repository
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd trading_bot
```

### 2. ติดตั้ง Dependencies
```bash
pip install -r requirements.txt
```

### 3. ตั้งค่า Environment Variables
คัดลอกไฟล์ตัวอย่าง `.env.example` ไปเป็น `.env`:
```bash
cp .env.example .env
```
เปิดไฟล์ `.env` แล้วใส่ Google Gemini API Key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
APP_MODE=paper
INITIAL_BALANCE=100000.0
MAX_RISK_PER_TRADE_PCT=2.0
STOP_LOSS_PCT=3.0
TAKE_PROFIT_PCT=6.0
MAX_DAILY_LOSS_PCT=5.0
```
*(หมายเหตุ: หากไม่ใส่ API Key ระบบจะใช้โหมด Heuristic Engine อัตโนมัติ)*

ตัวเลือกเพิ่มเติม (ดูทั้งหมดใน `.env.example`):

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
| --- | --- | --- |
| `PIPELINE_INTERVAL_MINUTES` | `0` | รัน Pipeline อัตโนมัติทุก N นาที (`0` = กดรันเองเท่านั้น) |
| `RISK_CHECK_INTERVAL_SECONDS` | `60` | ตรวจ Stop Loss / Take Profit อัตโนมัติทุก N วินาที (`0` = ปิด) |
| `ALLOW_SYNTHETIC_TRADING` | `false` | อนุญาตให้เทรดด้วยราคาจำลองเมื่อดึงราคาจริงไม่ได้ (Demo Offline เท่านั้น) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hostnames ที่เปิด Dashboard ได้ |
| `DASHBOARD_RELOAD` | `false` | Auto-reload เมื่อแก้โค้ด (สำหรับพัฒนา) |

### 4. รันระบบบอทและ Dashboard
```bash
python main.py
```

เปิดเบราว์เซอร์ไปที่:
👉 **http://localhost:8000**

### 5. รัน Tests
```bash
pip install -r requirements-dev.txt
pytest
```

---

## 🔒 Financial Safety Guardrails

1. **Paper Trading Only**: ตอนนี้มีเฉพาะ Paper Broker — หากตั้ง `APP_MODE` เป็นค่าอื่น ระบบจะไม่ยอมเริ่มทำงาน
2. **Position Sizing**: จำนวนหุ้นต่อไม้ = ค่าที่น้อยกว่าระหว่าง
   - ความเสี่ยงต่อไม้: `Equity × MAX_RISK_PER_TRADE_PCT ÷ ระยะ Stop Loss` และ
   - เพดานเงินลงทุนต่อหุ้น 1 ตัว: `Equity × 20% ÷ ราคา`

   ด้วยค่าเริ่มต้น (Risk 2%, Stop Loss 3%) เพดาน 20% จะเป็นตัวจำกัดเสมอ → แต่ละ Position มีมูลค่าประมาณ **20% ของพอร์ต** และขาดทุนสูงสุดเมื่อโดน Stop ≈ **0.6% ของพอร์ต** (ถือได้สูงสุด 5 ตัว)
3. **Stop Loss บังคับทุกออเดอร์**: คำนวณจากราคาที่ Fill จริง และมี Risk Monitor ตรวจอัตโนมัติเป็นระยะ
4. **Daily Loss Circuit Breaker**: หากขาดทุนวันนี้ (UTC) ถึง `MAX_DAILY_LOSS_PCT` บอทจะหยุดเปิด Position ใหม่จนถึงวันถัดไป (ยังปิด Position ได้ตามปกติ)
5. **ไม่เทรดด้วยข้อมูลจำลอง**: หากดึงราคาจาก Yahoo ไม่ได้ ระบบจะไม่คัดกรอง/ไม่ส่งคำสั่งซื้อด้วยราคาจำลอง (ยกเว้นเปิด `ALLOW_SYNTHETIC_TRADING`) และหากไม่มีข่าวจริง Sentiment จะเป็น NEUTRAL
6. **Dashboard Protection**: ฟังที่ `127.0.0.1` เป็นค่าเริ่มต้น, ตรวจ Host (กัน DNS Rebinding) และบล็อกคำขอ POST/WebSocket ข้ามเว็บ (กัน CSRF) — ยังไม่มีระบบ Login จึงไม่ควรเปิดให้เข้าถึงจากอินเทอร์เน็ต
7. **Secret Protection**: ป้องกัน API Key ด้วย `.env` และ `.gitignore` ไม่มีการบันทึกลง Git

---

## 📄 License
MIT License
