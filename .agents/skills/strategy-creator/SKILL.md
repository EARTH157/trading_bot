---
name: strategy-creator
description: >-
  Use this skill when the user wants to implement, customize, or add a new trading strategy to the trading bot.
---

# Strategy Creator Skill

คู่มือสำหรับ AI ในการสร้างหรือแก้ไขกลยุทธ์การเทรดให้เข้ากับสถาปัตยกรรมของบอท

## ขั้นตอนการสร้างกลยุทธ์ใหม่ (Steps)

1. **สืบทอดจาก StrategyBase**:
   - กลยุทธ์ใหม่ต้องสืบทอดมาจาก `core.interfaces.strategy.StrategyBase`
   - ต้องตั้งชื่อ Class ให้สื่อความหมาย เช่น `EmaCrossoverStrategy`, `RsiMeanReversionStrategy`

2. **Implement เมธอดสำคัญ**:
   - `calculate_indicators(df: pd.DataFrame) -> pd.DataFrame`: คำนวณค่า Indicator ที่จำเป็น เช่น EMA, RSI, ATR
   - `generate_signals(df: pd.DataFrame) -> SignalType`: ส่งค่าสัญญาณ `BUY`, `SELL`, หรือ `HOLD`
   - `get_stop_loss_price(entry_price: float, ...) -> float`: คำนวณราคา Stop Loss อัตโนมัติ

3. **กำหนด Strategy Parameters**:
   - พารามิเตอร์ต้องมี Default Values ที่สมเหตุสมผล และสามารถปรับแต่งได้จาก Config / Dashboard

4. **เพิ่มลงใน Registry**:
   - นำกลยุทธ์ไปลงทะเบียนใน `core/strategies/__init__.py` เพื่อให้ระบบหลักและหน้า Dashboard ค้นพบอัตโนมัติ
