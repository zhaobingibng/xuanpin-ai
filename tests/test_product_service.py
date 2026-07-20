"""Tests for async ProductService."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crawler.models.schemas import RawProduct
from app.database.base import Base
from app.models.product import Product
from app.services.product_service import ProductService


@pytest.fixture
async def async_session():
    """Provide a clean in-memory async SQLite session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Create ────────────────────────────────────────────────────


class TestProductServiceCreate:
    async def test_create_product(self, async_session):
        svc = ProductService(async_session)
        product = await svc.create(
            name="无线蓝牙耳机",
            platform="抖音",
            shop="数码旗舰店",
            price=199.0,
            viewers=500,
            sales_24h=120,
        )
        assert product.id is not None
        assert product.name == "无线蓝牙耳机"
        assert product.platform == "抖音"
        assert product.price == 199.0

    async def test_create_with_optional_fields(self, async_session):
        svc = ProductService(async_session)
        product = await svc.create(
            name="手机壳",
            platform="快手",
            shop="配件小店",
            image="https://img.example.com/case.jpg",
            price=19.9,
            viewers=0,
            sales_24h=0,
            ai_score=7.2,
        )
        assert product.image == "https://img.example.com/case.jpg"
        assert product.ai_score == 7.2


# ── Read ──────────────────────────────────────────────────────


class TestProductServiceRead:
    async def test_get_by_id(self, async_session):
        svc = ProductService(async_session)
        created = await svc.create(name="测试", platform="淘宝", shop="店铺", price=10.0)
        found = await svc.get_by_id(created.id)
        assert found is not None
        assert found.name == "测试"

    async def test_get_by_id_not_found(self, async_session):
        svc = ProductService(async_session)
        result = await svc.get_by_id(9999)
        assert result is None

    async def test_list_all(self, async_session):
        svc = ProductService(async_session)
        await svc.create(name="A", platform="抖音", shop="店A", price=1.0)
        await svc.create(name="B", platform="快手", shop="店B", price=2.0)
        await svc.create(name="C", platform="抖音", shop="店C", price=3.0)

        all_products = await svc.list_all()
        assert len(all_products) == 3

    async def test_list_filter_by_platform(self, async_session):
        svc = ProductService(async_session)
        await svc.create(name="A", platform="抖音", shop="店A", price=1.0)
        await svc.create(name="B", platform="快手", shop="店B", price=2.0)
        await svc.create(name="C", platform="抖音", shop="店C", price=3.0)

        results = await svc.list_all(platform="抖音")
        assert len(results) == 2
        assert all(p.platform == "抖音" for p in results)

    async def test_list_pagination(self, async_session):
        svc = ProductService(async_session)
        for i in range(10):
            await svc.create(name=f"商品{i}", platform="淘宝", shop="店铺", price=float(i))

        page = await svc.list_all(limit=3, offset=2)
        assert len(page) == 3
        assert page[0].name == "商品2"


# ── Update ────────────────────────────────────────────────────


class TestProductServiceUpdate:
    async def test_update_product(self, async_session):
        svc = ProductService(async_session)
        product = await svc.create(name="旧名称", platform="抖音", shop="店铺", price=50.0)

        updated = await svc.update(product.id, name="新名称", price=88.8)
        assert updated is not None
        assert updated.name == "新名称"
        assert updated.price == 88.8

    async def test_update_not_found(self, async_session):
        svc = ProductService(async_session)
        result = await svc.update(9999, name="不存在")
        assert result is None


# ── Delete ────────────────────────────────────────────────────


class TestProductServiceDelete:
    async def test_delete_product(self, async_session):
        svc = ProductService(async_session)
        product = await svc.create(name="要删除", platform="淘宝", shop="店铺", price=1.0)

        deleted = await svc.delete(product.id)
        assert deleted is True

        found = await svc.get_by_id(product.id)
        assert found is None

    async def test_delete_not_found(self, async_session):
        svc = ProductService(async_session)
        result = await svc.delete(9999)
        assert result is False


# ── Save Raw Products (Ingestion) ────────────────────────────


def _raw(**overrides) -> RawProduct:
    defaults = {
        "name": "蓝牙耳机降噪",
        "platform": "xiaohongshu",
        "shop": "数码旗舰店",
        "price": 99.9,
        "viewers": 1200,
        "sales_24h": 350,
        "url": "https://xhslink.com/p/1",
    }
    defaults.update(overrides)
    return RawProduct(**defaults)


class TestSaveRawProducts:
    async def test_save_single_product(self, async_session):
        svc = ProductService(async_session)
        raws = [_raw()]
        count = await svc.save_raw_products(raws)

        assert count == 1
        all_products = await svc.list_all()
        assert len(all_products) == 1
        p = all_products[0]
        assert p.platform == "xiaohongshu"
        assert p.price == 99.9
        assert p.url == "https://xhslink.com/p/1"

    async def test_save_multiple_products(self, async_session):
        svc = ProductService(async_session)
        raws = [
            _raw(name="蓝牙耳机A", url="https://xhslink.com/p/1"),
            _raw(name="蓝牙耳机B", url="https://xhslink.com/p/2"),
            _raw(name="蓝牙耳机C", url="https://xhslink.com/p/3"),
        ]
        count = await svc.save_raw_products(raws)

        assert count == 3
        all_products = await svc.list_all()
        assert len(all_products) == 3

    async def test_empty_list_returns_zero(self, async_session):
        svc = ProductService(async_session)
        count = await svc.save_raw_products([])
        assert count == 0

    async def test_url_dedup_updates_existing(self, async_session):
        svc = ProductService(async_session)

        # First save
        raws1 = [_raw(name="蓝牙耳机V1", price=99.9, url="https://xhslink.com/p/1")]
        await svc.save_raw_products(raws1)

        # Second save with same URL but different data
        raws2 = [_raw(name="蓝牙耳机V2", price=199.0, url="https://xhslink.com/p/1")]
        count = await svc.save_raw_products(raws2)

        assert count == 1  # 1 updated
        all_products = await svc.list_all()
        assert len(all_products) == 1
        # Should be updated to V2
        p = all_products[0]
        assert p.price == 199.0

    async def test_name_platform_dedup_when_no_url(self, async_session):
        svc = ProductService(async_session)

        # First save: no URL
        raws1 = [_raw(name="水杯保温", url=None, price=29.9, shop="家居店")]
        await svc.save_raw_products(raws1)

        # Second save: same name+platform, no URL, different price
        raws2 = [_raw(name="水杯保温", url=None, price=39.9, shop="家居店")]
        count = await svc.save_raw_products(raws2)

        assert count == 1  # 1 updated
        all_products = await svc.list_all()
        assert len(all_products) == 1
        assert all_products[0].price == 39.9

    async def test_invalid_name_dropped(self, async_session):
        svc = ProductService(async_session)
        raws = [
            _raw(name="蓝牙耳机"),
            _raw(name="包邮秒杀清仓爆款新款"),  # All ad words → empty after clean
            _raw(name="另一个水杯", url="https://xhslink.com/p/2"),
        ]
        count = await svc.save_raw_products(raws)

        assert count == 2
        all_products = await svc.list_all()
        assert len(all_products) == 2

    async def test_category_assigned(self, async_session):
        svc = ProductService(async_session)
        raws = [
            _raw(name="机械键盘青轴", url="https://xhslink.com/kb"),
        ]
        await svc.save_raw_products(raws)

        all_products = await svc.list_all()
        assert all_products[0].category == "数码"

    async def test_url_persisted(self, async_session):
        svc = ProductService(async_session)
        raws = [_raw(url="https://xhslink.com/persist")]
        await svc.save_raw_products(raws)

        all_products = await svc.list_all()
        assert all_products[0].url == "https://xhslink.com/persist"

    async def test_price_and_sales_converted(self, async_session):
        svc = ProductService(async_session)
        raws = [_raw(price=199.0, sales_24h=500, viewers=3200)]
        await svc.save_raw_products(raws)

        all_products = await svc.list_all()
        p = all_products[0]
        assert isinstance(p.price, float)
        assert p.price == 199.0
        assert isinstance(p.sales_24h, int)
        assert p.sales_24h == 500
        assert isinstance(p.viewers, int)
        assert p.viewers == 3200

    async def test_batch_dedup_same_name_shop_platform(self, async_session):
        """Pipeline batch-dedup filters duplicates within same batch."""
        svc = ProductService(async_session)
        raws = [
            _raw(name="蓝牙耳机", shop="店A", url=None),
            _raw(name="蓝牙耳机", shop="店A", url=None),  # dup within batch
        ]
        count = await svc.save_raw_products(raws)

        # Pipeline dedup by (name, shop, platform) removes the second
        assert count == 1

    async def test_cross_call_upsert_by_url(self, async_session):
        """Two separate save calls with same URL → one record in DB."""
        svc = ProductService(async_session)

        await svc.save_raw_products([_raw(name="商品A", price=10.0, url="https://xhslink.com/same")])
        await svc.save_raw_products([_raw(name="商品B", price=20.0, url="https://xhslink.com/same")])

        all_products = await svc.list_all()
        assert len(all_products) == 1
        assert all_products[0].price == 20.0  # updated

    async def test_different_urls_not_deduped(self, async_session):
        """Different URLs → separate records even with same name."""
        svc = ProductService(async_session)
        raws = [
            _raw(name="同款商品", shop="店A", url="https://xhslink.com/aaa"),
            _raw(name="同款商品", shop="店B", url="https://xhslink.com/bbb"),
        ]
        count = await svc.save_raw_products(raws)

        assert count == 2
        all_products = await svc.list_all()
        assert len(all_products) == 2
