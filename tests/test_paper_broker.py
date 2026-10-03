from core.brokers.paper_broker import PaperBroker
from core.interfaces.broker import OrderRequest, OrderSide, OrderStatus
from database.db_manager import db_manager


async def test_buy_and_sell_bookkeeping(fresh_state, quotes):
    broker = fresh_state
    quotes["AAPL"] = 100.0
    res = await broker.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, quantity=10))
    assert res.status == OrderStatus.FILLED
    assert broker.cash_balance == 99_000.0

    quotes["AAPL"] = 110.0
    res = await broker.place_order(OrderRequest(symbol="AAPL", side=OrderSide.SELL, quantity=10))
    assert res.status == OrderStatus.FILLED
    assert broker.cash_balance == 100_100.0
    assert broker.realized_pnl == 100.0
    assert broker.positions == {}


async def test_buy_rejected_on_synthetic_quote(fresh_state, quotes):
    res = await fresh_state.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, quantity=1))
    assert res.status == OrderStatus.REJECTED
    assert fresh_state.cash_balance == 100_000.0


async def test_sell_falls_back_to_last_known_price(fresh_state, quotes):
    broker = fresh_state
    quotes["AAPL"] = 100.0
    await broker.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, quantity=5))
    del quotes["AAPL"]  # Yahoo ล่ม -> ราคาจำลอง

    results = await broker.close_all_positions()

    assert results[0].status == OrderStatus.FILLED
    assert results[0].filled_price == 100.0
    assert broker.cash_balance == 100_000.0


async def test_rejected_sell_is_recorded(fresh_state, quotes):
    quotes["AAPL"] = 100.0
    res = await fresh_state.place_order(OrderRequest(symbol="AAPL", side=OrderSide.SELL, quantity=1))
    assert res.status == OrderStatus.REJECTED
    orders = await db_manager.get_recent_orders()
    assert orders[0]["status"] == "REJECTED"


async def test_state_survives_restart(fresh_state, quotes):
    broker = fresh_state
    quotes["AAPL"] = 100.0
    quotes["MSFT"] = 50.0
    await broker.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, quantity=10, stop_loss_price=97.0))
    await broker.place_order(OrderRequest(symbol="MSFT", side=OrderSide.BUY, quantity=4))
    quotes["MSFT"] = 60.0
    await broker.place_order(OrderRequest(symbol="MSFT", side=OrderSide.SELL, quantity=4))

    restarted = PaperBroker()
    await restarted.load_state()

    assert restarted.cash_balance == broker.cash_balance == 99_040.0
    assert restarted.realized_pnl == 40.0
    assert set(restarted.positions) == {"AAPL"}
    assert restarted.positions["AAPL"].quantity == 10
    assert restarted.positions["AAPL"].stop_loss_price == 97.0


async def test_get_account_does_not_write_snapshots(fresh_state, quotes):
    from sqlalchemy import select, func
    from database.models import PortfolioSnapshotModel

    for _ in range(5):
        await fresh_state.get_account()

    async with db_manager.session_factory() as session:
        count = (await session.execute(select(func.count()).select_from(PortfolioSnapshotModel))).scalar()
    assert count == 0
