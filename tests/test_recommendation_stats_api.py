"""Tests for GET /recommendations/stats endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeSessionCtx:
    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *exc):
        return False


def _mock_factory():
    def factory():
        return _FakeSessionCtx()
    return factory


def _mock_generate_result(items: list[dict]) -> dict:
    return {
        "date": "2026-07-19",
        "total": len(items),
        "items": items,
    }


class TestStatsEndpoint:
    """统计接口。"""

    @pytest.mark.asyncio
    async def test_stats_returns_action_counts(self):
        """GET /recommendations/stats 应返回各 action 的计数。"""
        items = [
            {"action": "SELL", "rank": 1},
            {"action": "SELL", "rank": 2},
            {"action": "TEST", "rank": 3},
            {"action": "WATCH", "rank": 4},
            {"action": "WATCH", "rank": 5},
            {"action": "WATCH", "rank": 6},
            {"action": "DROP", "rank": 7},
        ]
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = _mock_generate_result(items)

        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch(
                "app.services.recommendation.daily_recommendation.DailyRecommendationService",
                return_value=mock_svc,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sell"] == 2
        assert data["test"] == 1
        assert data["watch"] == 3
        assert data["drop"] == 1

    @pytest.mark.asyncio
    async def test_stats_all_zeros_when_empty(self):
        """无商品时所有计数为 0。"""
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = _mock_generate_result([])

        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch(
                "app.services.recommendation.daily_recommendation.DailyRecommendationService",
                return_value=mock_svc,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {"sell": 0, "test": 0, "watch": 0, "drop": 0}


class TestStatsEmpty:
    """空数据。"""

    @pytest.mark.asyncio
    async def test_stats_error_returns_500(self):
        """服务异常时返回 500。"""
        mock_svc = AsyncMock()
        mock_svc.generate.side_effect = RuntimeError("db error")

        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch(
                "app.services.recommendation.daily_recommendation.DailyRecommendationService",
                return_value=mock_svc,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/stats")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "获取推荐统计失败"


class TestStatsFields:
    """字段完整。"""

    @pytest.mark.asyncio
    async def test_stats_has_all_keys(self):
        """返回应包含 sell/test/watch/drop 四个键。"""
        items = [{"action": "SELL", "rank": 1}]
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = _mock_generate_result(items)

        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch(
                "app.services.recommendation.daily_recommendation.DailyRecommendationService",
                return_value=mock_svc,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/stats")

        data = resp.json()
        expected_keys = {"sell", "test", "watch", "drop"}
        assert set(data.keys()) == expected_keys
