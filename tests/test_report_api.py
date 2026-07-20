"""Tests for DailyReport API endpoint (GET /reports/daily)."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeSessionCtx:
    """Minimal async context manager that yields a mock session."""

    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *exc):
        return False


def _mock_factory():
    """Return a callable that acts like async_sessionmaker."""

    def factory():
        return _FakeSessionCtx()

    return factory


def _sample_report(limit: int = 2) -> dict:
    """Return a sample daily report dict."""
    items = [
        {
            "rank": i + 1,
            "product_id": i + 1,
            "name": f"商品{i + 1}",
            "platform": "抖音",
            "image": f"https://img.example.com/{i + 1}.jpg",
            "price": 99.0 + i * 10,
            "score": 90 - i * 5,
            "level": "爆款" if i == 0 else "潜力",
            "reasons": ["销量高", "增长快"],
        }
        for i in range(limit)
    ]
    return {
        "date": date.today().isoformat(),
        "total": limit,
        "hot_products": 1 if limit > 0 else 0,
        "potential_products": min(limit - 1, 1) if limit > 0 else 0,
        "average_score": round(sum(item["score"] for item in items) / len(items), 1) if items else 0.0,
        "items": items,
    }


@pytest.mark.anyio
async def test_daily_report_empty():
    """GET /reports/daily with no data should return empty report structure."""
    empty_report = _sample_report(0)

    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = empty_report
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == date.today().isoformat()
    assert data["total"] == 0
    assert data["hot_products"] == 0
    assert data["potential_products"] == 0
    assert data["average_score"] == 0.0
    assert data["items"] == []


@pytest.mark.anyio
async def test_daily_report_with_data():
    """GET /reports/daily with data should return report items."""
    report = _sample_report(2)

    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = report
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["hot_products"] == 1
    assert data["potential_products"] == 1
    assert data["average_score"] == 87.5
    assert len(data["items"]) == 2
    assert data["items"][0]["rank"] == 1
    assert data["items"][0]["name"] == "商品1"
    assert data["items"][0]["score"] == 90
    assert data["items"][0]["level"] == "爆款"
    assert data["items"][1]["rank"] == 2
    assert data["items"][1]["level"] == "潜力"


@pytest.mark.anyio
async def test_daily_report_limit_param():
    """GET /reports/daily?limit=50 should pass limit to service."""
    report = _sample_report(3)

    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = report
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily?limit=50")

    assert resp.status_code == 200
    mock_svc.generate.assert_awaited_once_with(limit=50)


@pytest.mark.anyio
async def test_daily_report_default_limit():
    """GET /reports/daily without limit should default to 20."""
    report = _sample_report(2)

    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = report
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 200
    mock_svc.generate.assert_awaited_once_with(limit=20)


@pytest.mark.anyio
async def test_daily_report_fields_complete():
    """GET /reports/daily response should contain all required top-level and item-level fields."""
    report = _sample_report(1)

    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.return_value = report
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 200
    data = resp.json()

    # top-level fields
    top_keys = {"date", "total", "hot_products", "potential_products", "average_score", "items"}
    assert set(data.keys()) == top_keys

    # item-level fields
    item_keys = {"rank", "product_id", "name", "platform", "image", "price", "score", "level", "reasons"}
    assert set(data["items"][0].keys()) == item_keys

    # type checks
    assert isinstance(data["date"], str)
    assert isinstance(data["total"], int)
    assert isinstance(data["hot_products"], int)
    assert isinstance(data["potential_products"], int)
    assert isinstance(data["average_score"], float)
    assert isinstance(data["items"], list)
    assert isinstance(data["items"][0]["reasons"], list)


@pytest.mark.anyio
async def test_daily_report_service_exception():
    """GET /reports/daily should return 500 when service raises an exception."""
    with (
        patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
        patch("app.api.reports.DailyReportService") as mock_svc_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.generate.side_effect = RuntimeError("DB connection failed")
        mock_svc_cls.return_value = mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 500
    data = resp.json()
    assert data["detail"] == "生成日报失败"


@pytest.mark.anyio
async def test_daily_report_session_factory_exception():
    """GET /reports/daily should return 500 when session factory fails."""

    def bad_factory():
        raise RuntimeError("engine error")

    with patch("app.api.reports.get_async_session_factory", return_value=bad_factory):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")

    assert resp.status_code == 500
    data = resp.json()
    assert data["detail"] == "生成日报失败"
