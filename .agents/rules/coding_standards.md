# Python Coding Standards for Trading Bot

1. **Type Hints & Documentation**
   - ฟังก์ชันและเมธอดทุกตัวต้องมี Python Type Hints (เช่น `def execute_order(symbol: str, qty: float) -> OrderResult:`)
   - มี Docstrings อธิบาย Input, Output และวัตถุประสงค์สั้นๆ

2. **Error Handling & Resilience**
   - ฟังก์ชันที่เรียกใช้ Network/API (ดึงราคา, ส่งออเดอร์) ต้องมี `try...except` ดักจับข้อผิดพลาดพร้อม Log อย่างละเอียด
   - บอทต้องไม่ Crash เมื่อ Network หลุดหรือ API Timeout (ต้องมี Retry หรือ Fallback)

3. **Asynchronous & Non-Blocking**
   - ส่วนของ Web Dashboard และ WebSocket Streaming ต้องเป็น non-blocking (asyncio / FastAPI)
   - ไม่บล็อก Main Thread ของระบบคำนวณราคา
