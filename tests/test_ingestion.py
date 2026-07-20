"""Integration tests for the data ingestion pipeline.

End-to-end flow: Crawler → RawProduct → ProductService → SQLite → Query Product.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crawler.models.schemas import RawProduct
from app.database.base import Base
from app.models.product import Product
from app.services.product_service import ProductService


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
async def session():
    """Clean in-memory async SQLite session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Helpers ──────────────────────────────────────────────────


def _simulate_crawler_output(items: list[dict]) -> list[RawProduct]:
    """Simulate crawler output — a list of RawProduct."""
    products = []
    for item in items:
        products.append(RawProduct(
            name=item.get("name", "测试商品"),
            platform=item.get("platform", "xiaohongshu"),
            shop=item.get("shop", "测试店铺"),
            price=item.get("price", 99.9),
            viewers=item.get("viewers", 1000),
            sales_24h=item.get("sales_24h", 200),
            image=item.get("image"),
            url=item.get("url"),
            category=item.get("category", ""),
        ))
    return products


# ── TestEndToEndIngestion ───────────────────────────────────


class TestEndToEndIngestion:
    """Full pipeline: Crawler → RawProduct → ProductService → SQLite → Query."""

    @pytest.mark.anyio
    async def test_full_pipeline_single_product(self, session):
        svc = ProductService(session)

        raws = _simulate_crawler_output([
            {
                "name": "蓝牙耳机降噪",
                "platform": "xiaohongshu",
                "shop": "数码旗舰店",
                "price": 199.9,
                "viewers": 5000,
                "sales_24h": 800,
                "image": "https://img.example.com/earphone.jpg",
                "url": "https://xhslink.com/product/1",
            },
        ])

        saved = await svc.save_raw_products(raws)
        assert saved == 1

        # Query from DB
        stmt = select(Product).where(Product.url == "https://xhslink.com/product/1")
        result = await session.execute(stmt)
        product = result.scalar_one()

        assert product.name == "蓝牙耳机降噪"
        assert product.platform == "xiaohongshu"
        assert product.shop == "数码旗舰店"
        assert product.price == 199.9
        assert product.viewers == 5000
        assert product.sales_24h == 800
        assert product.image == "https://img.example.com/earphone.jpg"
        assert product.url == "https://xhslink.com/product/1"
        assert product.category == "数码"
        assert product.id is not None

    @pytest.mark.anyio
    async def test_full_pipeline_batch(self, session):
        svc = ProductService(session)

        raws = _simulate_crawler_output([
            {"name": "机械键盘青轴", "url": "https://xhslink.com/kb", "price": 299.0},
            {"name": "保温水杯500ml", "url": "https://xhslink.com/cup", "price": 49.9},
            {"name": "运动鞋跑步鞋", "url": "https://xhslink.com/shoe", "price": 399.0},
            {"name": "充电宝20000毫安", "url": "https://xhslink.com/power", "price": 129.0},
        ])

        saved = await svc.save_raw_products(raws)
        assert saved == 4

        # Verify all in DB
        stmt = select(Product).order_by(Product.id)
        result = await session.execute(stmt)
        products = result.scalars().all()

        assert len(products) == 4
        names = [p.name for p in products]
        assert "机械键盘青轴" in names
        assert "保温水杯500ml" in names
        assert "运动鞋跑步鞋" in names
        assert "充电宝20000毫安" in names

    @pytest.mark.anyio
    async def test_re_crawl_updates_existing(self, session):
        svc = ProductService(session)

        # First crawl
        raws1 = _simulate_crawler_output([
            {"name": "蓝牙耳机V1", "url": "https://xhslink.com/p/1", "price": 99.9, "sales_24h": 100},
        ])
        saved1 = await svc.save_raw_products(raws1)
        assert saved1 == 1

        # Get ID from first crawl
        stmt = select(Product).where(Product.url == "https://xhslink.com/p/1")
        result = await session.execute(stmt)
        first_product = result.scalar_one()
        original_id = first_product.id

        # Second crawl — same URL, updated data
        raws2 = _simulate_crawler_output([
            {"name": "蓝牙耳机V2", "url": "https://xhslink.com/p/1", "price": 199.0, "sales_24h": 500},
        ])
        saved2 = await svc.save_raw_products(raws2)
        assert saved2 == 1

        # Verify: still 1 product, data updated, same ID
        result = await session.execute(stmt)
        updated_product = result.scalar_one()

        assert updated_product.id == original_id
        assert updated_product.price == 199.0
        assert updated_product.sales_24h == 500

        # No duplicate
        count_stmt = select(Product)
        count_result = await session.execute(count_stmt)
        assert len(count_result.scalars().all()) == 1

    @pytest.mark.anyio
    async def test_mixed_valid_and_invalid(self, session):
        svc = ProductService(session)

        raws = _simulate_crawler_output([
            {"name": "正常商品耳机", "url": "https://xhslink.com/ok"},
            {"name": "包邮秒杀清仓爆款新款", "url": "https://xhslink.com/bad"},  # all ad words
            {"name": "另一个水杯", "url": "https://xhslink.com/cup"},
        ])

        saved = await svc.save_raw_products(raws)
        assert saved == 2

        stmt = select(Product).order_by(Product.id)
        result = await session.execute(stmt)
        products = result.scalars().all()
        assert len(products) == 2

    @pytest.mark.anyio
    async def test_multi_platform_ingestion(self, session):
        svc = ProductService(session)

        raws = _simulate_crawler_output([
            {"name": "蓝牙耳机XHS", "platform": "xiaohongshu", "url": "https://xhslink.com/p/1"},
            {"name": "蓝牙耳机DY", "platform": "douyin", "url": "https://dylink.com/p/1"},
            {"name": "蓝牙耳机KS", "platform": "kuaishou", "url": "https://kslink.com/p/1"},
        ])

        saved = await svc.save_raw_products(raws)
        assert saved == 3

        stmt = select(Product).order_by(Product.platform)
        result = await session.execute(stmt)
        products = result.scalars().all()

        platforms = [p.platform for p in products]
        assert "douyin" in platforms
        assert "kuaishou" in platforms
        assert "xiaohongshu" in platforms

    @pytest.mark.anyio
    async def test_empty_crawl_output(self, session):
        svc = ProductService(session)
        saved = await svc.save_raw_products([])
        assert saved == 0

    @pytest.mark.anyio
    async def test_name_cleans_emoji_and_ads(self, session):
        svc = ProductService(session)

        raws = _simulate_crawler_output([
            {"name": "🔥爆款蓝牙耳机降噪", "url": "https://xhslink.com/clean"},
        ])

        await svc.save_raw_products(raws)

        stmt = select(Product).where(Product.url == "https://xhslink.com/clean")
        result = await session.execute(stmt)
        product = result.scalar_one()

        # emoji and "爆款" removed
        assert product.name == "蓝牙耳机降噪"
        assert "🔥" not in product.name
        assert "爆款" not in product.name

    @pytest.mark.anyio
    async def test_no_url_uses_name_platform_dedup(self, session):
        svc = ProductService(session)

        # First crawl: no URL
        raws1 = _simulate_crawler_output([
            {"name": "水杯保温", "url": None, "price": 29.9},
        ])
        await svc.save_raw_products(raws1)

        # Second crawl: same name + platform, no URL, different price
        raws2 = _simulate_crawler_output([
            {"name": "水杯保温", "url": None, "price": 39.9},
        ])
        await svc.save_raw_products(raws2)

        # Should be 1 product (updated by name+platform dedup)
        stmt = select(Product)
        result = await session.execute(stmt)
        products = result.scalars().all()

        assert len(products) == 1
        assert products[0].price == 39.9

    @pytest.mark.anyio
    async def test_sales_wan_format_converted(self, session):
        svc = ProductService(session)

        raws = [RawProduct(
            name="蓝牙耳机",
            platform="xiaohongshu",
            shop="数码店",
            price=99.9,
            sales_24h="1.2万",  # type: ignore[arg-type]
            url="https://xhslink.com/wan",
        )]

        await svc.save_raw_products(raws)

        stmt = select(Product).where(Product.url == "https://xhslink.com/wan")
        result = await session.execute(stmt)
        product = result.scalar_one()

        assert product.sales_24h == 12000
