from datetime import datetime

from core.agents.risk_guardian import RiskExecutionAgent
from core.interfaces.broker import OrderRequest, OrderSide


def _buy_candidate(symbol: str, score: float = 0.5):
    return {"symbol": symbol, "recommendation": "BUY", "combined_score": score, "current_price": 1.0}


def test_position_size_capped_by_allocation():
    agent = RiskExecutionAgent()
    # Risk 2% / Stop 3% -> 66% ของพอร์ต แต่เพดาน 20% ต้องเป็นตัวจำกัด
    assert agent.position_size(equity=100_000, price=100.0) == 200
    assert agent.position_size(equity=100_000, price=0) == 0


def test_exit_levels():
    assert RiskExecutionAgent.exit_levels(100.0) == (97.0, 106.0)


async def test_buy_uses_live_price_and_sets_exits_from_fill(fresh_state, quotes):
    broker = fresh_state
    quotes["AAPL"] = 200.0
    agent = RiskExecutionAgent()

    result = await agent.run({"screening_results": [_buy_candidate("AAPL")]})

    assert len(result.data["executed_orders"]) == 1
    pos = broker.positions["AAPL"]
    assert pos.quantity == 100  # 20% ของ 100,000 / 200
    assert pos.stop_loss_price == 194.0
    assert pos.take_profit_price == 212.0


async def test_no_buy_on_synthetic_price(fresh_state, quotes):
    agent = RiskExecutionAgent()  # quotes ว่าง = ทุกราคาเป็น Synthetic
    result = await agent.run({"screening_results": [_buy_candidate("AAPL")]})

    assert result.data["executed_orders"] == []
    assert fresh_state.positions == {}


async def test_circuit_breaker_blocks_new_buys(fresh_state, quotes):
    broker = fresh_state
    quotes["MSFT"] = 100.0
    broker.day_start_date = datetime.utcnow().strftime("%Y-%m-%d")
    broker.day_start_equity = 110_000.0  # ขาดทุนวันนี้ ~9% > 5%

    result = await RiskExecutionAgent().run({"screening_results": [_buy_candidate("MSFT")]})

    assert result.status == "WARNING"
    assert result.data["executed_orders"] == []
    assert "Circuit Breaker" in result.data["rejected_reasons"][0]


async def test_stop_request_blocks_new_buys(fresh_state, quotes):
    import asyncio
    quotes["MSFT"] = 100.0
    stop = asyncio.Event()
    stop.set()

    result = await RiskExecutionAgent().run({"screening_results": [_buy_candidate("MSFT")], "stop_event": stop})

    assert result.data["executed_orders"] == []
    assert fresh_state.positions == {}


async def test_enforce_exits_triggers_stop_loss(fresh_state, quotes):
    broker = fresh_state
    quotes["NVDA"] = 100.0
    await broker.place_order(OrderRequest(
        symbol="NVDA", side=OrderSide.BUY, quantity=10, stop_loss_price=97.0, take_profit_price=106.0
    ))
    quotes["NVDA"] = 96.0

    executed = await RiskExecutionAgent().enforce_exits()

    assert executed and "Stop Loss" in executed[0]
    assert "NVDA" not in broker.positions
    assert round(broker.realized_pnl, 2) == -40.0
