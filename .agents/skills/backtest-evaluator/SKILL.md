---
name: backtest-evaluator
description: >-
  Use this skill when running, evaluating, or analyzing backtest performance results for trading strategies.
---

# Backtest Evaluator Skill

คู่มือสำหรับประเมินผลการทดสอบกลยุทธ์ย้อนหลัง (Backtesting Performance)

## ดัชนีชี้วัดที่ต้องรายงาน (Key Metrics)

เมื่อผู้ใช้สั่งให้ Backtest กลยุทธ์ ให้สรุปผลลัพธ์ผ่านตัวชี้วัดดังต่อไปนี้เสมอ:
1. **Total Return (%)**: ผลตอบแทนรวมเทียบกับ Buy & Hold ของสินทรัพย์อ้างอิง
2. **Win Rate (%)**: อัตราการชนะ (จำนวนไม้กำไร / จำนวนไม้ทั้งหมด)
3. **Profit Factor**: กำไรรวม / ขาดทุนรวม (ควรมากกว่า 1.5)
4. **Max Drawdown (MDD %)**: การย่อตัวสูงสุดของพอร์ตจากจุดสูงสุด (ไม่ควรเกิน 15-20% สำหรับระบบความเสี่ยงต่ำ-ปานกลาง)
5. **Sharpe Ratio**: ผลตอบแทนเทียบกับความผันผวน (ค่า > 1.0 ถือว่าดี, > 2.0 ดีมาก)
6. **Total Trades**: จำนวนไม้ทั้งหมดที่เทรด เพื่อป้องกันปัญหา Overfitting หรือข้อมูลตัวอย่างน้อยเกินไป

## แนวทางการให้คำแนะนำ
- หาก Win Rate สูงแต่ Profit Factor ต่ำ: เตือนเรื่องการปล่อยให้ไม้ขาดทุนลากยาว (Risk-Reward Ratio ไม่ดี)
- หาก Trades น้อยเกินไป: เตือนว่าเงื่อนไขอาจตึงเกินไป (Over-filtering)
