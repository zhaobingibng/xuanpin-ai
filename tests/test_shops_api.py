"""Tests for Shops API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.main import app
from app.database.base import Base
from app.models.shop_registry import ShopRegistry


# ── Helpers ────────────────────────────────────────────────────


class _FakeSessionCtx:
    """Wraps an AsyncSession for use as async context manager."""
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args) -> None:
        pass


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _mock_factory(session):
    """Return a callable that returns _FakeSessionCtx."""
    def factory():
        return _FakeSessionCtx(session)
    return factory


# ── GET /api/shops ─────────────────────────────────────────────


class TestListShops:
    """GET /api/shops 店铺列表。"""

    async def test_empty_list(self, session):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.get("/api/shops")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_data(self, session):
        # Seed data
        shop = ShopRegistry(
            platform="taobao", shop_id="t1", shop_name="测试店",
            fans=100, priority=2, enabled=True, monitor_strategy="daily",
        )
        session.add(shop)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.get("/api/shops")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["shop_name"] == "测试店"
        assert data[0]["platform"] == "taobao"
        expected_keys = {
            "id", "platform", "shop_id", "shop_name", "shop_url",
            "category", "fans", "priority", "enabled", "last_scan_at",
            "monitor_strategy", "created_at", "updated_at",
        }
        assert set(data[0].keys()) == expected_keys


# ── POST /api/shops ────────────────────────────────────────────


class TestCreateShop:
    """POST /api/shops 创建店铺。"""

    async def test_create_success(self, session):
        payload = {
            "platform": "taobao",
            "shop_id": "shop_001",
            "shop_name": "新店",
            "fans": 500,
            "priority": 2,
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.post("/api/shops", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["shop_name"] == "新店"
        assert data["fans"] == 500
        assert data["priority"] == 2
        assert data["id"] is not None

    async def test_create_duplicate(self, session):
        shop = ShopRegistry(
            platform="taobao", shop_id="dup1", shop_name="已有店",
            fans=0, priority=1, enabled=True, monitor_strategy="daily",
        )
        session.add(shop)
        await session.commit()

        payload = {"platform": "taobao", "shop_id": "dup1", "shop_name": "重复"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.post("/api/shops", json=payload)
        assert resp.status_code == 409
        assert "已存在" in resp.json()["detail"]

    async def test_create_minimal(self, session):
        payload = {"platform": "tmall", "shop_id": "tm1", "shop_name": "天猫店"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.post("/api/shops", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["monitor_strategy"] == "daily"


# ── PATCH /api/shops/{id} ──────────────────────────────────────


class TestUpdateShop:
    """PATCH /api/shops/{id} 更新店铺。"""

    async def test_update_success(self, session):
        shop = ShopRegistry(
            platform="taobao", shop_id="up1", shop_name="原名",
            fans=10, priority=1, enabled=True, monitor_strategy="daily",
        )
        session.add(shop)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.patch(f"/api/shops/{shop.id}", json={"shop_name": "新名", "fans": 999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["shop_name"] == "新名"
        assert data["fans"] == 999

    async def test_update_nonexistent(self, session):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.patch("/api/shops/9999", json={"shop_name": "不存在"})
        assert resp.status_code == 404

    async def test_update_empty_body(self, session):
        shop = ShopRegistry(
            platform="taobao", shop_id="up2", shop_name="空更新",
            fans=0, priority=1, enabled=True, monitor_strategy="daily",
        )
        session.add(shop)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.patch(f"/api/shops/{shop.id}", json={})
        assert resp.status_code == 400


# ── DELETE /api/shops/{id} ─────────────────────────────────────


class TestDeleteShop:
    """DELETE /api/shops/{id} 删除店铺。"""

    async def test_delete_success(self, session):
        shop = ShopRegistry(
            platform="taobao", shop_id="del1", shop_name="待删",
            fans=0, priority=1, enabled=True, monitor_strategy="daily",
        )
        session.add(shop)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.delete(f"/api/shops/{shop.id}")
        assert resp.status_code == 200
        assert "已删除" in resp.json()["message"]

    async def test_delete_nonexistent(self, session):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.api.shops.get_async_session_factory", return_value=_mock_factory(session)):
                resp = await client.delete("/api/shops/9999")
        assert resp.status_code == 404
