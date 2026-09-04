# Trading Bot Workspace Guidelines (GEMINI.md)

คุณคือ AI Assistant สำหรับโปรเจกต์พัฒนาระบบ **Multi-Market Stock Trading Bot พร้อม Web Dashboard**

## 1. กฎความปลอดภัยสูงสุด (Financial Safety Guardrails)
- **Paper Trading First**: ทุกคำสั่งเทรดต้องมีค่าเริ่มต้นเป็นโหมด Paper Trading / Simulation เสมอ ห้ามเปิด Live Trading โดยไม่มีการยืนยันอย่างชัดเจน
- **Strict Risk Management**: โค้ดของ Strategy ทุกตัวต้องบังคับให้มี:
  - Stop Loss เสมอ
  - Position Sizing (ห้าม All-in หรือซื้อเกินเปอร์เซ็นต์พอร์ตที่กำหนด เช่น จำกัดไม่เกิน 2-5% ของพอร์ตต่อออเดอร์)
- **Secrets & Credentials**: ห้ามเขียน API Key, Secret Token, รหัสผ่าน หรือข้อมูลอ่อนไหวลงในโค้ดโดยตรง ต้องอ่านผ่าน Environment Variables (`.env`) เท่านั้น

## 2. มาตรฐานสถาปัตยกรรม (Architecture Standards)
- **Modular & Abstract**: 
  - Broker ต้องสืบทอดจาก `core.interfaces.broker.BrokerBase`
  - Data Feed ต้องสืบทอดจาก `core.interfaces.data_feed.DataFeedBase`
  - Strategy ต้องสืบทอดจาก `core.interfaces.strategy.StrategyBase`
- **Supported Markets**:
  1. Paper Simulator (Yahoo Finance / Synthetic Feed)
  2. US Stocks (Alpaca Markets API)
  3. Thai Stocks (SETTRADE Open API)
- **Tech Stack**:
  - Python 3.10+ (Type Hinting ครบถ้วน)
  - FastAPI สำหรับ Web Dashboard & Real-time WebSockets
  - SQLite (ผ่าน SQLAlchemy หรือ aiosqlite) สำหรับบันทึกออเดอร์และสถานะพอร์ต
  - TradingView Lightweight Charts + Tailwind CSS สำหรับ Frontend Dashboard
