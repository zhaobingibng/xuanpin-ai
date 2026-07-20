"""Tests for GET /recommendations/opportunities endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


def _mock_daily_result(items: list[dict]) -> dict:
    """构造 DailyRecommendationService.generate() 的返回值。"""
    return {
        "date": "2026-07-19",
        "total": len(items),
        "items": items,
    }


def _make_item(
    pid: int,
    name: str,
    score: int,
    recommend_score: float,
    competition_score: int,
    market_level: str = "MEDIUM",
    action: str = "WATCH",
    price: float = 99.0,
) -> dict:
    return {
        "product_id": pid,
        "name": name,
        "platform": "xiaohongshu",
        "image": "",
        "price": price,
        "score": score,
        "level": "潜力",
        "reasons": ["好"],
        "lifecycle": "HOT",
        "competition_score": competition_score,
        "market_level": market_level,
        "action": action,
        "decision": {"action": action, "confidence": 80, "reason": ["高评分"]},
        "trend_score": 60.0,
        "recommend_score": recommend_score,
        "rank": pid,
        "status": "ACTIVE",
    }


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


# ── Endpoint tests ────────────────────────────────────────


@pytest.mark.anyio
async def test_opportunities_returns_200():
    """接口正常返回 200。"""
    items = [_make_item(1, "蓝牙耳机", 95, 90.0, 85, "LOW", "SELL")]
    mock_svc = MagicMock()
    mock_svc.generate = AsyncMock(return_value=_mock_daily_result(items))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.recommendations.get_async_session_factory", return_value=mock_factory),
        patch(
            "app.services.recommendation.daily_recommendation.DailyRecommendationService",
            return_value=mock_svc,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/recommendations/opportunities")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


@pytest.mark.anyio
async def test_opportunities_sorting():
    """按 opportunity_score = recommend_score×0.7 + competition_score×0.3 排序。"""
    items = [
        _make_item(1, "商品A", 80, 60.0, 30),  # opp = 42+9 = 51
        _make_item(2, "商品B", 90, 80.0, 90),  # opp = 56+27 = 83
        _make_item(3, "商品C", 70, 50.0, 80),  # opp = 35+24 = 59
    ]
    mock_svc = MagicMock()
    mock_svc.generate = AsyncMock(return_value=_mock_daily_result(items))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.recommendations.get_async_session_factory", return_value=mock_factory),
        patch(
            "app.services.recommendation.daily_recommendation.DailyRecommendationService",
            return_value=mock_svc,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/recommendations/opportunities")

    data = resp.json()
    assert len(data) == 3
    # 商品B (83) > 商品C (59) > 商品A (51)
    assert data[0]["name"] == "商品B"
    assert data[1]["name"] == "商品C"
    assert data[2]["name"] == "商品A"
    # rank 应递增
    assert [d["rank"] for d in data] == [1, 2, 3]


@pytest.mark.anyio
async def test_opportunities_field_completeness():
    """返回的每条记录应包含所有必需字段。"""
    items = [_make_item(1, "蓝牙耳机", 95, 90.0, 85, "LOW", "SELL", 199.0)]
    mock_svc = MagicMock()
    mock_svc.generate = AsyncMock(return_value=_mock_daily_result(items))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.recommendations.get_async_session_factory", return_value=mock_factory),
        patch(
            "app.services.recommendation.daily_recommendation.DailyRecommendationService",
            return_value=mock_svc,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/recommendations/opportunities")

    data = resp.json()
    assert len(data) == 1
    item = data[0]

    expected_keys = {
        "rank", "name", "price", "score",
        "recommend_score", "competition_score",
        "market_level", "action", "reasons",
    }
    assert set(item.keys()) == expected_keys
    assert item["rank"] == 1
    assert item["name"] == "蓝牙耳机"
    assert item["price"] == 199.0
    assert item["score"] == 95
    assert item["recommend_score"] == 90.0
    assert item["competition_score"] == 85
    assert item["market_level"] == "LOW"
    assert item["action"] == "SELL"
    assert isinstance(item["reasons"], list)


@pytest.mark.anyio
async def test_opportunities_empty():
    """无推荐数据时返回空列表。"""
    mock_svc = MagicMock()
    mock_svc.generate = AsyncMock(return_value=_mock_daily_result([]))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.recommendations.get_async_session_factory", return_value=mock_factory),
        patch(
            "app.services.recommendation.daily_recommendation.DailyRecommendationService",
            return_value=mock_svc,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/recommendations/opportunities")

    assert resp.status_code == 200
    assert resp.json() == []
