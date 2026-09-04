---
name: risk-auditor
description: >-
  Use this skill to audit, review, or verify trading bot code for financial safety, risk controls, and position sizing.
---

# Risk Auditor Skill

คู่มือสำหรับตรวจสอบความเสี่ยงของโค้ดก่อนนำไปรันจริง (Risk & Safety Audit)

## จุดตรวจเช็คความเสี่ยง (Audit Checklist)

1. **Position Sizing Check**:
   - บอทมีโมดูลคำนวณขนาดไม้ตาม % ความเสี่ยงต่อพอร์ตหรือไม่ (เช่น 1-2% Risk per trade)
   - ไม่มีการฮาร์ดโค้ดซื้อเต็มจำนวนเงินในพอร์ต (No All-In)
2. **Stop Loss Enforcement**:
   - ทุกครั้งที่มีการเปิด Position ต้องมีเงื่อนไข Stop Loss ชัดเจน
   - มีกลไก Trailing Stop หรือ Take Profit รองรับหรือไม่
3. **Execution Mode Check**:
   - ตรวจสอบว่า `mode` ของบอทเป็น `paper` หรือไม่ ป้องกันการยิงไปที่ Live API โดยไม่ตั้งใจ
4. **Circuit Breaker / Daily Loss Limit**:
   - หากพอร์ตติดลบเกินค่าที่กำหนดใน 1 วัน (เช่น ขาดทุนถึง 5% ของพอร์ต) บอทต้องหยุดรับออเดอร์ใหม่ทันที
