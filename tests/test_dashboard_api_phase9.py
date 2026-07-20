"""Tests for Dashboard API endpoints (Phase 9.6.7)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.crawler_status import CrawlerStatus


class _FakeSessionCtx:
    """Fake async session context manager."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


# ── GET /dashboard/overview ──────────────────────────────


@pytest.mark.anyio
async def test_dashboard_overview():
    """GET /dashboard/overview should return system statistics."""
    mock_session = MagicMock()

    overview_data = {
        "products": 150,
        "today_crawl": 3,
        "hot_products": 20,
        "rising_products": 35,
        "today_recommendations": 50,
        "average_score": 72.5,
        "platform_distribution": {"小红书": 80, "抖音": 50, "快手": 20},
        "category_distribution": {"数码": 60, "家居": 40, "服饰": 30, "其他": 20},
    }

    mock_service = MagicMock()
    mock_service.overview = AsyncMock(return_value=overview_data)

    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.dashboard.get_async_session_factory", return_value=mock_factory),
        patch("app.api.dashboard.DashboardService", return_value=mock_service),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["products"] == 150
    assert data["today_crawl"] == 3
    assert data["hot_products"] == 20
    assert data["rising_products"] == 35
    assert data["today_recommendations"] == 50
    assert data["average_score"] == 72.5
    assert data["platform_distribution"]["小红书"] == 80
    assert data["category_distribution"]["数码"] == 60


@pytest.mark.anyio
async def test_dashboard_overview_empty():
    """GET /dashboard/overview with empty DB should return zeros."""
    mock_session = MagicMock()

    overview_data = {
        "products": 0,
        "today_crawl": 0,
        "hot_products": 0,
        "rising_products": 0,
        "today_recommendations": 0,
        "average_score": 0.0,
        "platform_distribution": {},
        "category_distribution": {},
    }

    mock_service = MagicMock()
    mock_service.overview = AsyncMock(return_value=overview_data)

    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.dashboard.get_async_session_factory", return_value=mock_factory),
        patch("app.api.dashboard.DashboardService", return_value=mock_service),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["products"] == 0
    assert data["platform_distribution"] == {}


# ── GET /dashboard/crawler-status ────────────────────────


def _mock_crawler_status(cid: int, platform: str, status: str, total: int = 100) -> MagicMock:
    r = MagicMock(spec=CrawlerStatus)
    r.id = cid
    r.platform = platform
    r.last_run_time = datetime(2026, 7, 19, 12, 0, cid)
    r.status = status
    r.total = total
    r.success = int(total * 0.9) if status == "SUCCESS" else 0
    r.failed = int(total * 0.1) if status == "FAILED" else 0
    r.message = None
    return r


@pytest.mark.anyio
async def test_crawler_status_list():
    """GET /dashboard/crawler-status should return recent records."""
    mock_session = MagicMock()

    records = [
        _mock_crawler_status(3, "kuaishou", "SUCCESS", 80),
        _mock_crawler_status(2, "douyin", "FAILED", 100),
        _mock_crawler_status(1, "xhs", "SUCCESS", 120),
    ]

    mock_repo = MagicMock()
    mock_repo.get_latest = AsyncMock(return_value=records)

    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.dashboard.get_async_session_factory", return_value=mock_factory),
        patch("app.api.dashboard.CrawlerStatusRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard/crawler-status")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["platform"] == "kuaishou"
    assert data[0]["status"] == "SUCCESS"
    assert data[1]["platform"] == "douyin"
    assert data[1]["status"] == "FAILED"
    assert data[2]["platform"] == "xhs"


@pytest.mark.anyio
async def test_crawler_status_empty():
    """GET /dashboard/crawler-status with no records should return empty list."""
    mock_session = MagicMock()

    mock_repo = MagicMock()
    mock_repo.get_latest = AsyncMock(return_value=[])

    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.dashboard.get_async_session_factory", return_value=mock_factory),
        patch("app.api.dashboard.CrawlerStatusRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard/crawler-status")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_crawler_status_with_limit():
    """GET /dashboard/crawler-status?limit=5 should pass limit parameter."""
    mock_session = MagicMock()

    records = [_mock_crawler_status(i, f"p{i}", "SUCCESS", 50) for i in range(5)]

    mock_repo = MagicMock()
    mock_repo.get_latest = AsyncMock(return_value=records)

    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.dashboard.get_async_session_factory", return_value=mock_factory),
        patch("app.api.dashboard.CrawlerStatusRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard/crawler-status?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    mock_repo.get_latest.assert_called_once_with(limit=5)
