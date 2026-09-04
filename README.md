# 🚀 AI Multi-Agent Stock Trading Bot & Web Dashboard

ระบบเทรดหุ้นอัตโนมัติด้วยสถาปัตยกรรม **4 Autonomous AI Agents** ทำงานร่วมกันแบบ Real-time พร้อม **Web Dashboard** มอนิเตอร์พอร์ตและกระบวนการคิดของ AI วินาทีต่อวินาที

---

## 🌟 ฟีเจอร์หลัก (Core Features)

- **4 Autonomous AI Collaborative Pipeline**:
  1. 🤖 **Agent 1 (News Scout)**: สแกนข่าวการเงินล่าสุดและ RSS Feed บันทึกเป็นเอกสาร Markdown ชั่วคราว
  2. 🧠 **Agent 2 (Sentiment Analyst)**: วิเคราะห์แนวโน้มข่าวด้วย **Google Gemini 2.5 Flash** สกัดปัจจัยบวก (Catalysts) และความเสี่ยง (Risks)
  3. 📊 **Agent 3 (Market Screener)**: คำนวณอินดิเคเตอร์ทางเทคนิค (EMA 20/50, RSI 14, ATR) ผสานคะแนน Sentiment เพื่อจัดอันดับหุ้นน่าลงทุน
  4. 🛡️ **Agent 4 (Risk Guardian)**: ผู้พิทักษ์ความเสี่ยง คำนวณ Position Sizing (สูงสุดไม่เกิน 2% ของพอร์ตต่อไม้), บังคับตั้งราคา Stop Loss (3%) และ Take Profit (6%)
- **Live AI Cognitive Stream**: กล่องคอนโซลเรดาร์แสดงกระบวนการคิดและข้อความตัดสินใจของ AI สดๆ วินาทีต่อวินาที
- **Real-Time Visual State Animations**: การ์ด AI ขยับแบบ Neon Glow Pulse เมื่อกำลังคิด และเปลี่ยนเป็นสีเขียว Done เมื่อวิเคราะห์เสร็จ
- **TradingView Lightweight Charts**: กราฟแท่งเทียนราคาหุ้นพร้อมเส้นค่าเฉลี่ย EMA 20 และ EMA 50
- **Paper Trading First**: ปลอดภัยด้วยระบบจำลองการเทรด (Virtual Balance \,000 USD)
- **Panic Button**: ปุ่ม Sell All ปิดทุกสถานะในพอร์ตทันทีในกรณีฉุกเฉิน

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, aiosqlite
- **AI / LLM**: Google Gemini 2.5 Flash (google-generativeai)
- **Market Data**: Yahoo Finance (yfinance), Synthetic Feed Fallback
- **Database**: SQLite
- **Frontend**: Tailwind CSS, TradingView Lightweight Charts, Lucide Icons, WebSocket Real-time Broadcasting

---

## 🚀 วิธีติดตั้งและเริ่มต้นใช้งาน (Quickstart)

### 1. โคลน Repository
`ash
git clone <YOUR_GITHUB_REPO_URL>
cd trading_bot
`

### 2. ติดตั้ง Dependencies
`ash
pip install -r requirements.txt
`

### 3. ตั้งค่า Environment Variables
คัดลอกไฟล์ตัวอย่าง .env.example ไปเป็น .env:
`ash
cp .env.example .env
`
เปิดไฟล์ .env แล้วใส่ Google Gemini API Key:
`env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
APP_MODE=paper
INITIAL_BALANCE=100000.0
MAX_RISK_PER_TRADE_PCT=2.0
STOP_LOSS_PCT=3.0
TAKE_PROFIT_PCT=6.0
`
*(หมายเหตุ: หากไม่ใส่ API Key ระบบจะใช้โหมด Heuristic Engine อัตโนมัติ)*

### 4. รันระบบบอทและ Dashboard
`ash
python main.py
`

เปิดเบราว์เซอร์ไปที่:
👉 **http://localhost:8000**

---

## 🔒 Financial Safety Guardrails

1. **Paper Trading Default**: ทุกคำสั่งเริ่มต้นในโหมดจำลองพอร์ตเสมอ
2. **Strict Risk Management**: บังคับจำกัดการขาดทุนด้วย Stop Loss และควบคุมขนาด Position Sizing ทุกออเดอร์
3. **Secret Protection**: ป้องกัน API Key ด้วย .env และ .gitignore ไม่มีการบันทึกลง Git

---

## 📄 License
MIT License
