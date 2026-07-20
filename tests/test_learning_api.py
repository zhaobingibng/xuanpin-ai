"""Tests for Learning API endpoints — config, optimize, history."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.scoring_config import ScoringConfig


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


def _mock_config(
    cid: int = 1, version: int = 1, is_active: bool = True,
    sales_w: float = 0.30, trend_w: float = 0.25,
) -> MagicMock:
    c = MagicMock(spec=ScoringConfig)
    c.id = cid
    c.name = "default"
    c.version = version
    c.is_active = is_active
    c.sales_weight = sales_w
    c.trend_weight = trend_w
    c.viewer_weight = 0.15
    c.price_weight = 0.15
    c.competition_weight = 0.15
    c.created_at = datetime(2026, 7, 19)
    c.to_weights_dict.return_value = {
        "sales_weight": sales_w,
        "trend_weight": trend_w,
        "viewer_weight": 0.15,
        "price_weight": 0.15,
        "competition_weight": 0.15,
    }
    return c


# ── GET /learning/config ─────────────────────────────────


@pytest.mark.anyio
async def test_learning_config():
    """GET /learning/config 返回当前评分权重。"""
    config = _mock_config()

    mock_repo = MagicMock()
    mock_repo.get_active = AsyncMock(return_value=config)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.learning.get_async_session_factory", return_value=mock_factory),
        patch("app.api.learning.ScoringRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/learning/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert data["is_active"] is True
    assert "weights" in data
    assert data["weights"]["sales_weight"] == 0.30


@pytest.mark.anyio
async def test_learning_config_no_active():
    """无活跃配置时返回默认权重。"""
    mock_repo = MagicMock()
    mock_repo.get_active = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.learning.get_async_session_factory", return_value=mock_factory),
        patch("app.api.learning.ScoringRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/learning/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 0
    assert data["is_active"] is False
    assert data["weights"]["sales_weight"] == 0.30


# ── POST /learning/optimize ──────────────────────────────


@pytest.mark.anyio
async def test_learning_optimize():
    """POST /learning/optimize 触发权重优化。"""
    opt_result = {
        "old_version": 1,
        "new_version": 2,
        "changes": {"sales_weight": "+2.0%", "trend_weight": "-1.0%"},
        "reason": "销量因素对成功推荐贡献最高",
    }

    mock_optimizer = AsyncMock()
    mock_optimizer.optimize = AsyncMock(return_value=opt_result)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.learning.get_async_session_factory", return_value=mock_factory),
        patch("app.api.learning.ScoringOptimizer", return_value=mock_optimizer),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/learning/optimize")

    assert resp.status_code == 200
    data = resp.json()
    assert data["old_version"] == 1
    assert data["new_version"] == 2
    assert "changes" in data
    assert "reason" in data


# ── GET /learning/history ────────────────────────────────


@pytest.mark.anyio
async def test_learning_history():
    """GET /learning/history 返回历史版本列表。"""
    configs = [
        _mock_config(cid=2, version=2, sales_w=0.35),
        _mock_config(cid=1, version=1, sales_w=0.30),
    ]

    mock_repo = MagicMock()
    mock_repo.get_history = AsyncMock(return_value=configs)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.learning.get_async_session_factory", return_value=mock_factory),
        patch("app.api.learning.ScoringRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/learning/history")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["version"] == 2
    assert data[1]["version"] == 1

    # 字段完整性
    for item in data:
        assert "id" in item
        assert "version" in item
        assert "is_active" in item
        assert "weights" in item
        assert "created_at" in item


@pytest.mark.anyio
async def test_learning_history_empty():
    """无历史记录时返回空列表。"""
    mock_repo = MagicMock()
    mock_repo.get_history = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.learning.get_async_session_factory", return_value=mock_factory),
        patch("app.api.learning.ScoringRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/learning/history")

    assert resp.status_code == 200
    assert resp.json() == []
