"""Tests for Strategy API endpoints — generate, history, 404."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.product_strategy import ProductStrategy


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


def _mock_product():
    p = MagicMock()
    p.id = 1
    p.name = "蓝牙耳机"
    p.price = 99.0
    p.sales_24h = 500
    p.ai_score = 85.0
    p.lifecycle_stage = "HOT"
    return p


def _mock_strategy_record(
    sid: int, product_id: int, title: str = "学生党必备降噪 蓝牙耳机"
) -> MagicMock:
    r = MagicMock(spec=ProductStrategy)
    r.id = sid
    r.product_id = product_id
    r.title = title
    r.selling_points = json.dumps(["高音质", "长续航"], ensure_ascii=False)
    r.xiaohongshu_copy = "小红书文案"
    r.xianyu_copy = "闲鱼文案"
    r.price_strategy = json.dumps({"cost": 60, "sell": 99, "profit": 39}, ensure_ascii=False)
    r.profit_analysis = json.dumps({"profit_margin": "39.4%"}, ensure_ascii=False)
    r.created_at = datetime(2026, 7, 19, 10, 0, 0)
    return r


# ── POST /strategy/generate ──────────────────────────────────


@pytest.mark.anyio
async def test_strategy_generate_success():
    """POST /strategy/generate 成功生成运营方案。"""
    strategy_result = {
        "product_id": 1,
        "title": "学生党必备降噪 蓝牙耳机",
        "selling_points": ["高音质", "长续航"],
        "xiaohongshu_copy": "小红书文案内容",
        "xianyu_copy": "闲鱼文案内容",
        "price_strategy": {"cost": 60, "sell": 99, "profit": 39},
        "profit_analysis": {"profit_margin": "39.4%"},
    }

    mock_product = _mock_product()
    mock_product_svc = MagicMock()
    mock_product_svc.get_by_id = AsyncMock(return_value=mock_product)

    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=strategy_result)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.strategy.get_async_session_factory", return_value=mock_factory),
        patch("app.services.product_service.ProductService", return_value=mock_product_svc),
        patch("app.api.strategy.ProductStrategyGenerator", return_value=mock_generator),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/strategy/generate", json={"product_id": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "学生党必备降噪 蓝牙耳机"
    assert len(data["selling_points"]) == 2
    assert "xiaohongshu_copy" in data
    assert "price_strategy" in data


@pytest.mark.anyio
async def test_strategy_generate_404():
    """POST /strategy/generate 商品不存在时返回 404。"""
    mock_product_svc = MagicMock()
    mock_product_svc.get_by_id = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.strategy.get_async_session_factory", return_value=mock_factory),
        patch("app.services.product_service.ProductService", return_value=mock_product_svc),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/strategy/generate", json={"product_id": 999})

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_strategy_generate_error():
    """POST /strategy/generate 异常时返回 500。"""
    mock_product_svc = MagicMock()
    mock_product_svc.get_by_id = AsyncMock(side_effect=RuntimeError("DB error"))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.strategy.get_async_session_factory", return_value=mock_factory),
        patch("app.services.product_service.ProductService", return_value=mock_product_svc),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/strategy/generate", json={"product_id": 1})

    assert resp.status_code == 500


# ── GET /strategy/{product_id} ────────────────────────────────


@pytest.mark.anyio
async def test_strategy_history_success():
    """GET /strategy/{product_id} 返回历史方案。"""
    records = [_mock_strategy_record(1, 1, "方案A"), _mock_strategy_record(2, 1, "方案B")]

    mock_repo = MagicMock()
    mock_repo.get_history = AsyncMock(return_value=records)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.strategy.get_async_session_factory", return_value=mock_factory),
        patch("app.api.strategy.StrategyRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/strategy/1")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "方案A"
    assert "selling_points" in data[0]
    assert "price_strategy" in data[0]
    assert "created_at" in data[0]


@pytest.mark.anyio
async def test_strategy_history_404():
    """GET /strategy/{product_id} 无数据时返回 404。"""
    mock_repo = MagicMock()
    mock_repo.get_history = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.strategy.get_async_session_factory", return_value=mock_factory),
        patch("app.api.strategy.StrategyRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/strategy/999")

    assert resp.status_code == 404
