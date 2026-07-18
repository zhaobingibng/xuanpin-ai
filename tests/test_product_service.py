"""Tests for async ProductService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
