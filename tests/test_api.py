"""Tests for FastAPI API endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.product import Product
from app.models.product_history import ProductHistory


def _mock_product(pid: int, name: str, platform: str = "抖音", price: float = 99.0, ai_score: float = 70.0, shop: str = "测试店铺", viewers: int = 100, sales_24h: int = 50) -> MagicMock:
    """Create a mock Product."""
    p = MagicMock(spec=Product)
    p.id = pid
    p.name = name
    p.platform = platform
    p.price = price
    p.ai_score = ai_score
    p.shop = shop
    p.viewers = viewers
    p.sales_24h = sales_24h
    return p


def _mock_history(hid: int, product_id: int, price: float, sales: int, viewers: int) -> MagicMock:
    """Create a mock ProductHistory."""
    from datetime import datetime, timedelta
    h = MagicMock(spec=ProductHistory)
    h.id = hid
    h.product_id = product_id
    h.price = price
    h.sales_24h = sales
    h.viewers = viewers
    h.ai_score = 60.0
    h.record_time = datetime(2026, 7, 1) + timedelta(days=hid)
    return h


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health():
    """GET /health should return status ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "xuanpin-ai"


@pytest.mark.anyio
async def test_products_empty():
    """GET /products with empty DB should return empty list."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = []

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_products_with_data():
    """GET /products with data should return product list."""
    p1 = _mock_product(1, "蓝牙耳机降噪", "抖音", 99.0)
    p2 = _mock_product(2, "保温水杯500ml", "小红书", 49.0)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = [p1, p2]

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[0]["name"] == "蓝牙耳机降噪"
    assert data[0]["platform"] == "抖音"
    assert data[0]["price"] == 99.0
    assert "category" in data[0]
    assert data[1]["id"] == 2


@pytest.mark.anyio
async def test_products_fields():
    """GET /products should return exactly the required fields."""
    p = _mock_product(5, "手机壳透明", "快手", 19.9)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = [p]

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products")

    data = resp.json()
    expected_keys = {"id", "name", "platform", "price", "category"}
    assert set(data[0].keys()) == expected_keys


@pytest.mark.anyio
async def test_ranking_empty():
    """GET /ranking/top100 with empty DB should return empty list."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # First query returns products (empty), second returns histories
    mock_session.query.return_value.all.return_value = []

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.ranking.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ranking/top100")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_ranking_with_data():
    """GET /ranking/top100 should return sorted ranking."""
    p1 = _mock_product(1, "蓝牙耳机", "抖音", 99.0, ai_score=90.0)
    p2 = _mock_product(2, "保温杯", "小红书", 49.0, ai_score=60.0)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Products query returns both products
    # History query returns empty
    def query_side_effect(model):
        mock_q = MagicMock()
        if model == Product:
            mock_q.all.return_value = [p1, p2]
        else:
            mock_q.all.return_value = []
        return mock_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.ranking.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ranking/top100")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["rank"] == 1
    assert data[0]["name"] == "蓝牙耳机"
    assert data[1]["rank"] == 2
    assert data[1]["name"] == "保温杯"


@pytest.mark.anyio
async def test_ranking_fields():
    """GET /ranking/top100 should return all required fields."""
    p = _mock_product(1, "测试商品", "抖音", 50.0, ai_score=80.0)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    def query_side_effect(model):
        mock_q = MagicMock()
        if model == Product:
            mock_q.all.return_value = [p]
        else:
            mock_q.all.return_value = []
        return mock_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.ranking.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ranking/top100")

    data = resp.json()
    expected_keys = {"rank", "name", "platform", "price", "ai_score", "trend_score", "final_score", "level"}
    assert set(data[0].keys()) == expected_keys
    assert data[0]["ai_score"] == 80.0
    assert "level" in data[0]


@pytest.mark.anyio
async def test_ranking_with_history():
    """GET /ranking/top100 should compute trend_score from history."""
    p = _mock_product(1, "爆款商品", "抖音", 80.0, ai_score=85.0)

    h1 = _mock_history(1, 1, 100.0, 50, 200)
    h2 = _mock_history(2, 1, 90.0, 100, 400)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    def query_side_effect(model):
        mock_q = MagicMock()
        if model == Product:
            mock_q.all.return_value = [p]
        else:
            mock_q.all.return_value = [h1, h2]
        return mock_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.ranking.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ranking/top100")

    data = resp.json()
    assert len(data) == 1
    # With rising sales (50→100) and rising views (200→400), trend_score > 50
    assert data[0]["trend_score"] > 50
    assert data[0]["ai_score"] == 85.0


@pytest.mark.anyio
async def test_product_by_id():
    """GET /products/{id} should return the product detail."""
    p = _mock_product(42, "蓝牙耳机降噪", "抖音", 99.0, ai_score=85.0, shop="数码旗舰店", viewers=500, sales_24h=120)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter_by.return_value.first.return_value = p

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/42")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 42
    assert data["name"] == "蓝牙耳机降噪"
    assert data["platform"] == "抖音"
    assert data["price"] == 99.0
    assert "category" in data
    assert "history" in data


@pytest.mark.anyio
async def test_product_by_id_not_found():
    """GET /products/{id} with nonexistent ID should return 404."""
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


@pytest.mark.anyio
async def test_categories_stats():
    """GET /products/categories should return category counts."""
    products = [
        _mock_product(1, "蓝牙耳机降噪"),
        _mock_product(2, "手机壳透明"),
        _mock_product(3, "充电宝大容量"),
        _mock_product(4, "保温水杯500ml"),
        _mock_product(5, "收纳盒桌面"),
        _mock_product(6, "衣服女装新款"),
    ]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = products

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/categories")

    assert resp.status_code == 200
    data = resp.json()
    assert data["数码"] == 3  # 蓝牙耳机, 手机壳, 充电宝
    assert data["家居"] == 2  # 保温水杯, 收纳盒
    assert data["服饰"] == 1  # 衣服


@pytest.mark.anyio
async def test_categories_empty():
    """GET /products/categories with empty DB should return empty dict."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.all.return_value = []

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/categories")

    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.anyio
async def test_product_trend_with_history():
    """GET /products/{id}/trend should return trend analysis."""
    p = _mock_product(1, "蓝牙耳机", "抖音", 99.0, ai_score=85.0)

    h1 = _mock_history(1, 1, 100.0, 50, 200)
    h2 = _mock_history(2, 1, 90.0, 100, 400)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # First query: Product by id
    product_q = MagicMock()
    product_q.filter_by.return_value.first.return_value = p
    # Second query: ProductHistory by product_id, with order_by and all
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
    assert data["level"] == "爆发"


@pytest.mark.anyio
async def test_product_trend_not_found():
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


@pytest.mark.anyio
async def test_product_detail_full():
    """GET /products/{id}/detail should return detail + trend + stats."""
    p1 = _mock_product(1, "蓝牙耳机降噪", "抖音", 99.0, ai_score=90.0, viewers=500, sales_24h=120)
    p2 = _mock_product(2, "保温水杯500ml", "小红书", 49.0, ai_score=70.0, viewers=200, sales_24h=80)
    p3 = _mock_product(3, "手机壳透明", "快手", 19.9, ai_score=60.0, viewers=100, sales_24h=30)

    h1 = _mock_history(1, 1, 100.0, 50, 200)
    h2 = _mock_history(2, 1, 90.0, 100, 400)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Product query: filter_by for product 1
    product_q = MagicMock()
    product_q.filter_by.return_value.first.return_value = p1

    # ProductHistory query
    history_q = MagicMock()
    history_q.filter_by.return_value.order_by.return_value.all.return_value = [h1, h2]

    # All products query
    all_q = MagicMock()
    all_q.all.return_value = [p1, p2, p3]

    call_count = {"n": 0}

    def query_side_effect(model):
        call_count["n"] += 1
        if model == Product:
            # First call: filter_by for single product
            # Second call: all() for stats
            if call_count["n"] == 1:
                return product_q
            return all_q
        return history_q

    mock_session.query.side_effect = query_side_effect

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/1/detail")

    assert resp.status_code == 200
    data = resp.json()

    # 商品详情
    assert data["id"] == 1
    assert data["name"] == "蓝牙耳机降噪"
    assert data["platform"] == "抖音"
    assert data["price"] == 99.0
    assert data["category"] == "数码"

    # 趋势数据
    assert "trend" in data
    assert "sales_growth" in data["trend"]
    assert "view_growth" in data["trend"]
    assert "level" in data["trend"]

    # 统计数据
    assert data["stats"]["total_products"] == 3
    assert data["stats"]["ai_rank"] == 1  # highest ai_score
    assert data["stats"]["avg_ai_score"] > 0


@pytest.mark.anyio
async def test_product_detail_not_found():
    """GET /products/{id}/detail with nonexistent product should return 404."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.api.products.get_session_factory", return_value=mock_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/products/9999/detail")

    assert resp.status_code == 404
