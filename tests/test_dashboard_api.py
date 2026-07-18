"""Tests for Dashboard API endpoints (Phase 8.1)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.product import Product
from app.models.product_history import ProductHistory


def _mock_product(pid: int, name: str, platform: str = "抖音", price: float = 99.0, ai_score: float = 70.0) -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = pid
    p.name = name
    p.platform = platform
    p.price = price
    p.ai_score = ai_score
    p.shop = "测试店铺"
    p.viewers = 100
    p.sales_24h = 50
    return p


def _mock_history(hid: int, product_id: int, price: float, sales: int, viewers: int, ai: float | None = 60.0, day_offset: int = 0) -> MagicMock:
    h = MagicMock(spec=ProductHistory)
    h.id = hid
    h.product_id = product_id
    h.price = price
    h.sales_24h = sales
    h.viewers = viewers
    h.ai_score = ai
    h.record_time = datetime(2026, 7, 1) + timedelta(days=day_offset)
    return h


# ── GET /products/{id} with history ──────────────────────────


@pytest.mark.anyio
async def test_product_detail_with_history():
    """GET /products/{id} should return product with history array."""
    p = _mock_product(1, "蓝牙耳机降噪", "抖音", 99.0, ai_score=85.0)
    h1 = _mock_history(1, 1, 100.0, 50, 200, ai=80.0, day_offset=0)
    h2 = _mock_history(2, 1, 95.0, 80, 300, ai=82.0, day_offset=1)
    h3 = _mock_history(3, 1, 99.0, 120, 500, ai=85.0, day_offset=2)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    product_q = MagicMock()
    product_q.filter_by.return_value.first.return_value = p

    history_q = MagicMock()
    history_q.filter_by.return_value.order_by.return_value.all.return_value = [h1, h2, h3]

    def query_side_effect(model):
        if model == Product:
            return product_q
        return history_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["name"] == "蓝牙耳机降噪"
    assert data["platform"] == "抖音"
    assert data["price"] == 99.0
    assert data["category"] == "数码"
    assert len(data["history"]) == 3
    # History should be time-ascending
    assert data["history"][0]["price"] == 100.0
    assert data["history"][2]["price"] == 99.0
    # Each history item has required fields
    for item in data["history"]:
        assert "price" in item
        assert "sales_24h" in item
        assert "viewers" in item
        assert "ai_score" in item
        assert "record_time" in item


@pytest.mark.anyio
async def test_product_detail_empty_history():
    """GET /products/{id} with no history should return empty history array."""
    p = _mock_product(5, "保温水杯", "小红书", 49.0)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    product_q = MagicMock()
    product_q.filter_by.return_value.first.return_value = p

    history_q = MagicMock()
    history_q.filter_by.return_value.order_by.return_value.all.return_value = []

    def query_side_effect(model):
        if model == Product:
            return product_q
        return history_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/5")

    assert resp.status_code == 200
    data = resp.json()
    assert data["history"] == []


@pytest.mark.anyio
async def test_product_detail_not_found():
    """GET /products/{id} with nonexistent product should return 404."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/9999")

    assert resp.status_code == 404


# ── GET /products/{id}/trend ─────────────────────────────────


@pytest.mark.anyio
async def test_trend_full_fields():
    """GET /products/{id}/trend should return all trend fields."""
    p = _mock_product(1, "蓝牙耳机", ai_score=85.0)
    h1 = _mock_history(1, 1, 100.0, 50, 200, day_offset=0)
    h2 = _mock_history(2, 1, 90.0, 100, 400, day_offset=1)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    product_q = MagicMock()
    product_q.filter_by.return_value.first.return_value = p

    history_q = MagicMock()
    history_q.filter_by.return_value.order_by.return_value.all.return_value = [h1, h2]

    def query_side_effect(model):
        if model == Product:
            return product_q
        return history_q

    mock_session.query.side_effect = query_side_effect
    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/1/trend")

    assert resp.status_code == 200
    data = resp.json()
    expected_keys = {"trend_score", "sales_growth", "view_growth", "price_change", "level"}
    assert set(data.keys()) == expected_keys
    assert isinstance(data["trend_score"], float)
    assert isinstance(data["level"], str)


@pytest.mark.anyio
async def test_trend_not_found():
    """GET /products/{id}/trend with nonexistent product should return 404."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/9999/trend")

    assert resp.status_code == 404


# ── GET /stats/category ──────────────────────────────────────


@pytest.mark.anyio
async def test_stats_category():
    """GET /stats/category should return category counts."""
    products = [
        _mock_product(1, "蓝牙耳机降噪"),
        _mock_product(2, "手机壳透明"),
        _mock_product(3, "保温水杯500ml"),
        _mock_product(4, "衣服女装"),
    ]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = products

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.stats.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/stats/category")

    assert resp.status_code == 200
    data = resp.json()
    assert data["数码"] == 2  # 蓝牙耳机, 手机壳
    assert data["家居"] == 1  # 保温水杯
    assert data["服饰"] == 1  # 衣服


@pytest.mark.anyio
async def test_stats_category_empty():
    """GET /stats/category with empty DB should return empty dict."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = []

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.stats.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/stats/category")

    assert resp.status_code == 200
    assert resp.json() == {}


# ── GET /stats/platform ──────────────────────────────────────


@pytest.mark.anyio
async def test_stats_platform():
    """GET /stats/platform should return platform counts."""
    products = [
        _mock_product(1, "商品A", "小红书"),
        _mock_product(2, "商品B", "小红书"),
        _mock_product(3, "商品C", "抖音"),
        _mock_product(4, "商品D", "快手"),
    ]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = products

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.stats.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/stats/platform")

    assert resp.status_code == 200
    data = resp.json()
    assert data["小红书"] == 2
    assert data["抖音"] == 1
    assert data["快手"] == 1


@pytest.mark.anyio
async def test_stats_platform_empty():
    """GET /stats/platform with empty DB should return empty dict."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = []

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.stats.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/stats/platform")

    assert resp.status_code == 200
    assert resp.json() == {}
