"""Tests for report history and detail API endpoints."""

from datetime import date
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


def _mock_report_summary(rid: int, d: str) -> MagicMock:
    r = MagicMock()
    r.id = rid
    r.report_date = date.fromisoformat(d)
    r.total = 10
    r.hot_products = 3
    r.potential_products = 4
    r.average_score = 75.5
    return r


def _mock_report_detail(rid: int, d: str) -> MagicMock:
    r = MagicMock()
    r.id = rid
    r.report_date = date.fromisoformat(d)
    r.total = 2
    r.hot_products = 1
    r.potential_products = 1
    r.average_score = 85.0

    item1 = MagicMock()
    item1.id = 1
    item1.product_id = 101
    item1.rank = 1
    item1.name = "爆款蓝牙耳机"
    item1.platform = "xiaohongshu"
    item1.image = "https://img.example.com/1.jpg"
    item1.price = 99.0
    item1.score = 90
    item1.level = "爆款"
    item1.reasons = '["销量高", "增长快"]'

    item2 = MagicMock()
    item2.id = 2
    item2.product_id = 102
    item2.rank = 2
    item2.name = "潜力水杯"
    item2.platform = "douyin"
    item2.image = ""
    item2.price = 49.0
    item2.score = 80
    item2.level = "潜力"
    item2.reasons = '["性价比高"]'

    r.items = [item1, item2]
    return r


class TestReportHistory:

    @pytest.mark.asyncio
    async def test_history_empty(self):
        """GET /reports/history with no data should return empty list."""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_history.return_value = []
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/history")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_with_data(self):
        """GET /reports/history should return report summaries."""
        reports = [
            _mock_report_summary(1, "2026-07-19"),
            _mock_report_summary(2, "2026-07-18"),
        ]
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_history.return_value = reports
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/history")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["report_date"] == "2026-07-19"
        assert data[0]["total"] == 10
        assert data[1]["report_date"] == "2026-07-18"

    @pytest.mark.asyncio
    async def test_history_limit_param(self):
        """GET /reports/history?limit=5 should pass limit to repo."""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_history.return_value = []
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/history?limit=5")

        assert resp.status_code == 200
        mock_repo.get_history.assert_awaited_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_history_fields(self):
        """GET /reports/history items should have correct fields."""
        reports = [_mock_report_summary(1, "2026-07-19")]
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_history.return_value = reports
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/history")

        data = resp.json()
        expected_keys = {"id", "report_date", "total", "hot_products", "potential_products", "average_score"}
        assert set(data[0].keys()) == expected_keys


class TestReportDetail:

    @pytest.mark.asyncio
    async def test_detail_found(self):
        """GET /reports/{id} should return report detail with items."""
        report = _mock_report_detail(1, "2026-07-19")
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_report_detail.return_value = report
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["report_date"] == "2026-07-19"
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["rank"] == 1
        assert data["items"][0]["name"] == "爆款蓝牙耳机"
        assert data["items"][0]["reasons"] == ["销量高", "增长快"]

    @pytest.mark.asyncio
    async def test_detail_not_found(self):
        """GET /reports/{id} with nonexistent id should return 404."""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_report_detail.return_value = None
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/999")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "日报不存在"

    @pytest.mark.asyncio
    async def test_detail_fields(self):
        """GET /reports/{id} items should have correct fields."""
        report = _mock_report_detail(1, "2026-07-19")
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.ReportRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_report_detail.return_value = report
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/1")

        data = resp.json()
        item_keys = {"id", "product_id", "rank", "name", "platform", "image", "price", "score", "level", "reasons"}
        assert set(data["items"][0].keys()) == item_keys

        top_keys = {"id", "report_date", "total", "hot_products", "potential_products", "average_score", "items"}
        assert set(data.keys()) == top_keys
