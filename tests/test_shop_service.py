"""Tests for ShopService — shop registry CRUD."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — ensure all models registered
from app.database.base import Base
from app.services.shop_service import ShopService


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


# ── Create ─────────────────────────────────────────────────────


class TestCreateShop:
    """create_shop() 基本功能。"""

    async def test_create_basic(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="taobao",
            shop_id="shop_001",
            shop_name="测试旗舰店",
        )
        assert shop.id is not None
        assert shop.platform == "taobao"
        assert shop.shop_id == "shop_001"
        assert shop.shop_name == "测试旗舰店"
        assert shop.enabled is True
        assert shop.priority == 1
        assert shop.monitor_strategy == "daily"

    async def test_create_with_all_fields(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="tmall",
            shop_id="tm_123",
            shop_name="天猫旗舰店",
            shop_url="https://shop.tmall.com/123",
            category="数码",
            fans=50000,
            priority=3,
            enabled=False,
            monitor_strategy="hourly",
        )
        assert shop.category == "数码"
        assert shop.fans == 50000
        assert shop.priority == 3
        assert shop.enabled is False
        assert shop.monitor_strategy == "hourly"
        assert shop.shop_url == "https://shop.tmall.com/123"


# ── Update ─────────────────────────────────────────────────────


class TestUpdateShop:
    """update_shop() 更新字段。"""

    async def test_update_single_field(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="u1", shop_name="原名")
        updated = await svc.update_shop(shop.id, shop_name="新名")
        assert updated is not None
        assert updated.shop_name == "新名"
        assert updated.platform == "taobao"  # unchanged

    async def test_update_multiple_fields(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="u2", shop_name="店A")
        updated = await svc.update_shop(shop.id, fans=999, priority=3, enabled=False)
        assert updated is not None
        assert updated.fans == 999
        assert updated.priority == 3
        assert updated.enabled is False

    async def test_update_nonexistent(self, session):
        svc = ShopService(session)
        result = await svc.update_shop(9999, shop_name="不存在")
        assert result is None

    async def test_update_ignores_none_values(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="u3", shop_name="店B", fans=100)
        updated = await svc.update_shop(shop.id, fans=None, shop_name="新店B")
        assert updated is not None
        assert updated.fans == 100  # unchanged
        assert updated.shop_name == "新店B"


# ── Delete ─────────────────────────────────────────────────────


class TestDeleteShop:
    """delete_shop() 删除记录。"""

    async def test_delete_existing(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="d1", shop_name="待删")
        result = await svc.delete_shop(shop.id)
        assert result is True
        # Verify gone
        found = await svc.get_shop(shop.id)
        assert found is None

    async def test_delete_nonexistent(self, session):
        svc = ShopService(session)
        result = await svc.delete_shop(9999)
        assert result is False


# ── Query ──────────────────────────────────────────────────────


class TestListShops:
    """list_enabled_shops() / list_all_shops() 查询。"""

    async def test_list_enabled(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="e1", shop_name="启用1", enabled=True)
        await svc.create_shop(platform="taobao", shop_id="e2", shop_name="启用2", enabled=True)
        await svc.create_shop(platform="taobao", shop_id="e3", shop_name="禁用1", enabled=False)
        enabled = await svc.list_enabled_shops()
        assert len(enabled) == 2

    async def test_list_enabled_by_platform(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="p1", shop_name="淘宝店")
        await svc.create_shop(platform="tmall", shop_id="p2", shop_name="天猫店")
        result = await svc.list_enabled_shops(platform="taobao")
        assert len(result) == 1
        assert result[0].platform == "taobao"

    async def test_list_all(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="a1", shop_name="店1", enabled=True)
        await svc.create_shop(platform="taobao", shop_id="a2", shop_name="店2", enabled=False)
        all_shops = await svc.list_all_shops()
        assert len(all_shops) == 2

    async def test_list_enabled_sorted_by_priority(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="s1", shop_name="低", priority=1)
        await svc.create_shop(platform="taobao", shop_id="s2", shop_name="高", priority=3)
        await svc.create_shop(platform="taobao", shop_id="s3", shop_name="中", priority=2)
        result = await svc.list_enabled_shops()
        assert result[0].priority == 3  # highest first
        assert result[-1].priority == 1


# ── Find ──────────────────────────────────────────────────────


class TestFindByShopId:
    """find_by_shop_id() 按平台+标识查找。"""

    async def test_find_existing(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="f001", shop_name="找到了")
        found = await svc.find_by_shop_id("taobao", "f001")
        assert found is not None
        assert found.shop_name == "找到了"

    async def test_find_wrong_platform(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="f002", shop_name="淘宝")
        found = await svc.find_by_shop_id("tmall", "f002")
        assert found is None

    async def test_find_nonexistent(self, session):
        svc = ShopService(session)
        found = await svc.find_by_shop_id("taobao", "nope")
        assert found is None


# ── Mark scanned ──────────────────────────────────────────────


class TestMarkScanned:
    """mark_scanned() 标记扫描时间。"""

    async def test_mark_scanned(self, session):
        from datetime import datetime

        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="ms1", shop_name="扫描测试")
        assert shop.last_scan_at is None

        now = datetime(2026, 7, 20, 12, 0, 0)
        updated = await svc.mark_scanned(shop.id, scan_time=now)
        assert updated is not None
        assert updated.last_scan_at == now

    async def test_mark_scanned_default_time(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(platform="taobao", shop_id="ms2", shop_name="默认时间")
        updated = await svc.mark_scanned(shop.id)
        assert updated is not None
        assert updated.last_scan_at is not None
