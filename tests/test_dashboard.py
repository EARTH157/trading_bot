import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(fresh_state, quotes):
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


def test_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.json()["account"]["cash_balance"] == 100_000.0


def test_websocket_loop_ends_when_client_disconnects(client):
    from dashboard.app import manager

    for _ in range(3):
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "TICK"

    # ให้ Server ประมวลผล Disconnect
    for _ in range(50):
        if not manager.active_connections:
            break
        asyncio.run(asyncio.sleep(0.05))
    assert manager.active_connections == {}


def test_cross_origin_post_is_blocked(client):
    res = client.post("/api/emergency/sell_all", headers={"Origin": "https://evil.example"})
    assert res.status_code == 403

    res = client.post("/api/emergency/sell_all", headers={"Origin": "http://testserver"})
    assert res.status_code == 200


def test_untrusted_host_is_blocked(client):
    res = client.get("/api/status", headers={"Host": "attacker.example"})
    assert res.status_code == 400


def test_news_file_rejects_unexpected_names(client):
    assert client.get("/api/news_file/..").status_code in (400, 404)
    assert client.get("/api/news_file/settings.py").status_code == 400
    assert client.get("/api/news_file/AAPL_20260101_000000.md").status_code == 404


def test_dashboard_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "lightweight-charts@4.2.3" in res.text
