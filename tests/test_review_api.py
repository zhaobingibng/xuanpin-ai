"""Tests for Review API endpoints — latest, accuracy, 404, field completeness."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.recommendation_review import RecommendationReview


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


def _mock_review(
    rid: int, product_id: int, review_date: date, result: str,
    sales_change: float = 10.0, trend_change: float = 5.0,
) -> MagicMock:
    r = MagicMock(spec=RecommendationReview)
    r.id = rid
    r.product_id = product_id
    r.review_date = review_date
    r.result = result
    r.sales_change = sales_change
    r.trend_change = trend_change
    return r


# ── GET /reviews/latest ──────────────────────────────────


@pytest.mark.anyio
async def test_reviews_latest_success():
    """GET /reviews/latest 正常返回最近复盘。"""
    today = date.today()
    records = [
        _mock_review(1, 10, today, "SUCCESS"),
        _mock_review(2, 20, today, "NORMAL"),
        _mock_review(3, 30, today, "FAILED"),
    ]

    mock_repo = MagicMock()
    mock_repo.get_reviews = AsyncMock(return_value=records)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.reviews.get_async_session_factory", return_value=mock_factory),
        patch("app.api.reviews.ReviewRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reviews/latest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == today.isoformat()
    assert data["total"] == 3
    assert data["success"] == 1
    assert data["normal"] == 1
    assert data["failed"] == 1
    assert len(data["items"]) == 3

    # 字段完整性
    for item in data["items"]:
        assert "id" in item
        assert "product_id" in item
        assert "result" in item
        assert "sales_change" in item
        assert "trend_change" in item


@pytest.mark.anyio
async def test_reviews_latest_404():
    """GET /reviews/latest 无记录时返回 404。"""
    mock_repo = MagicMock()
    mock_repo.get_reviews = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.reviews.get_async_session_factory", return_value=mock_factory),
        patch("app.api.reviews.ReviewRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reviews/latest")

    assert resp.status_code == 404


# ── GET /reviews/accuracy ────────────────────────────────


@pytest.mark.anyio
async def test_reviews_accuracy():
    """GET /reviews/accuracy 返回准确率统计。"""
    mock_repo = MagicMock()
    mock_repo.get_accuracy = AsyncMock(return_value={
        "accuracy": 75.0,
        "total": 100,
        "success": 75,
    })

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.reviews.get_async_session_factory", return_value=mock_factory),
        patch("app.api.reviews.ReviewRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reviews/accuracy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["accuracy"] == 75.0
    assert data["total"] == 100
    assert data["success"] == 75


@pytest.mark.anyio
async def test_reviews_accuracy_empty():
    """GET /reviews/accuracy 无数据时返回零。"""
    mock_repo = MagicMock()
    mock_repo.get_accuracy = AsyncMock(return_value={
        "accuracy": 0.0,
        "total": 0,
        "success": 0,
    })

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.reviews.get_async_session_factory", return_value=mock_factory),
        patch("app.api.reviews.ReviewRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reviews/accuracy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["accuracy"] == 0.0
    assert data["total"] == 0
