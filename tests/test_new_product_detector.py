"""Tests for Phase 14 Task 2: NewProductDetector service."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.product import Product
from app.models.shop_registry import ShopRegistry
from app.services.discovery.new_product_detector import NewProductDetector


@pytest.fixture
async def session():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def shop_with_products(session):
    """Create a shop and some products for testing."""
    # Create shop
    shop = ShopRegistry(
        platform="taobao",
        shop_id="test_shop_001",
        shop_name="测试旗舰店",
        shop_url="https://shop.taobao.com/test",
        category="蓝牙耳机",
        enabled=True,
        priority=3,
    )
    session.add(shop)
    await session.commit()
    await session.refresh(shop)

    # 设置 last_scan_at 为一个明确的历史时间
    scan_time = datetime.now()
    shop.last_scan_at = scan_time
    await session.commit()

    # 创建“旧”商品 — created_at 在 last_scan_at 之前
    old_products = [
        Product(name="旧商品1", platform="taobao", shop="测试旗舰店", price=99.0,
                created_at=scan_time - timedelta(days=2)),
        Product(name="旧商品2", platform="taobao", shop="测试旗舰店", price=149.0,
                created_at=scan_time - timedelta(days=1)),
    ]
    for p in old_products:
        session.add(p)
    await session.commit()

    # 创建“新”商品 — created_at 在 last_scan_at 之后
    new_products = [
        Product(name="新品1-蓝牙耳机", platform="taobao", shop="测试旗舰店", price=199.0,
                created_at=scan_time + timedelta(seconds=10)),
        Product(name="新品2-降噪耳机", platform="taobao", shop="测试旗舰店", price=299.0,
                created_at=scan_time + timedelta(seconds=20)),
    ]
    for p in new_products:
        session.add(p)
    await session.commit()

    return shop, old_products, new_products


class TestNewProductDetector:
    """NewProductDetector 测试。"""

    @pytest.mark.anyio
    async def test_detect_new_products(self, session, shop_with_products):
        """应检测到新品。"""
        shop, old_products, new_products = shop_with_products
        detector = NewProductDetector(session)

        result = await detector.detect_shop_new_products(shop.id)

        assert result["new_count"] == 2
        assert result["shop_name"] == "测试旗舰店"
        assert len(result["new_products"]) == 2

    @pytest.mark.anyio
    async def test_detect_updates_last_scan(self, session, shop_with_products):
        """检测后应更新 last_scan_at。"""
        shop, _, _ = shop_with_products
        old_scan_time = shop.last_scan_at
        detector = NewProductDetector(session)

        result = await detector.detect_shop_new_products(shop.id)

        await session.refresh(shop)
        assert shop.last_scan_at > old_scan_time

    @pytest.mark.anyio
    async def test_detect_nonexistent_shop(self, session):
        """不存在的店铺应返回空结果。"""
        detector = NewProductDetector(session)
        result = await detector.detect_shop_new_products(99999)

        assert result["new_count"] == 0
        assert result["new_products"] == []

    @pytest.mark.anyio
    async def test_detect_all_enabled_shops(self, session, shop_with_products):
        """应检测所有启用店铺的新品。"""
        shop, _, _ = shop_with_products
        detector = NewProductDetector(session)

        result = await detector.detect_all_enabled_shops(platform="taobao")

        assert result["total_shops"] >= 1
        assert result["total_new_products"] >= 2

    @pytest.mark.anyio
    async def test_detect_no_new_products(self, session):
        """首次扫描后无新品。"""
        # Create shop without products
        shop = ShopRegistry(
            platform="taobao",
            shop_id="empty_shop",
            shop_name="空店铺",
            enabled=True,
        )
        session.add(shop)
        await session.commit()

        detector = NewProductDetector(session)
        result = await detector.detect_shop_new_products(shop.id)

        assert result["new_count"] == 0
