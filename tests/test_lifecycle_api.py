"""Tests for lifecycle API endpoints — hot / rising."""

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


def _mock_product(pid: int, name: str, stage: str) -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.name = name
    p.platform = "xiaohongshu"
    p.price = 99.0
    p.sales_24h = 5000
    p.viewers = 10000
    p.lifecycle_stage = stage
    return p


class TestLifecycleHot:
    """GET /reports/lifecycle/hot。"""

    @pytest.mark.asyncio
    async def test_hot_with_data(self):
        """应返回 HOT 阶段的商品列表。"""
        products = [
            _mock_product(1, "爆款耳机", "HOT"),
            _mock_product(2, "爆款水杯", "HOT"),
        ]
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_hot_products.return_value = products
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/hot")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["name"] == "爆款耳机"
        assert data[0]["lifecycle_stage"] == "HOT"

    @pytest.mark.asyncio
    async def test_hot_empty(self):
        """无 HOT 商品时返回空列表。"""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_hot_products.return_value = []
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/hot")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_hot_fields(self):
        """返回的字段集合应正确。"""
        products = [_mock_product(1, "爆款耳机", "HOT")]
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_hot_products.return_value = products
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/hot")

        data = resp.json()
        expected_keys = {"id", "name", "platform", "price", "sales_24h", "viewers", "lifecycle_stage"}
        assert set(data[0].keys()) == expected_keys


class TestLifecycleRising:
    """GET /reports/lifecycle/rising。"""

    @pytest.mark.asyncio
    async def test_rising_with_data(self):
        """应返回 RISING 阶段的商品列表。"""
        products = [
            _mock_product(3, "上涨手机壳", "RISING"),
        ]
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_rising_products.return_value = products
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/rising")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 3
        assert data[0]["lifecycle_stage"] == "RISING"

    @pytest.mark.asyncio
    async def test_rising_empty(self):
        """无 RISING 商品时返回空列表。"""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_rising_products.return_value = []
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/rising")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_lifecycle_error_returns_500(self):
        """LifecycleRepository 异常时返回 500。"""
        with (
            patch("app.api.reports.get_async_session_factory", return_value=_mock_factory()),
            patch("app.api.reports.LifecycleRepository") as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_hot_products.side_effect = RuntimeError("db error")
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/reports/lifecycle/hot")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "获取热门商品失败"
