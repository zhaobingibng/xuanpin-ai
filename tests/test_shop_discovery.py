"""Tests for Phase 15 Task 3: ShopDiscoveryService — auto-discover & score shops."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.crawler.models.schemas import RawProduct
from app.database.base import Base
from app.services.discovery.shop_discovery import (
    ShopDiscoveryService,
    ShopScore,
    ShopStats,
)
from app.services.shop_service import ShopService


# ── Fixtures ──────────────────────────────────────────────────


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


def _make_product(
    name: str = "测试商品",
    shop: str = "测试店铺",
    platform: str = "taobao",
    price: float = 99.0,
    sales: int = 100,
    category: str = "数码",
    url: str | None = None,
) -> RawProduct:
    return RawProduct(
        name=name,
        platform=platform,
        shop=shop,
        price=price,
        sales_24h=sales,
        category=category,
        url=url or f"https://item.taobao.com/item.htm?id={hash(name)}",
    )


# ── ShopStats ─────────────────────────────────────────────────


class TestShopStats:
    """ShopStats 数据类测试。"""

    def test_category_count(self):
        stats = ShopStats(shop_name="test", platform="taobao")
        stats.categories = {"数码", "家居"}
        assert stats.category_count == 2

    def test_empty_categories(self):
        stats = ShopStats(shop_name="test", platform="taobao")
        assert stats.category_count == 0


# ── Aggregation ───────────────────────────────────────────────


class TestAggregation:
    """店铺数据聚合测试。"""

    def test_aggregate_single_shop(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name="商品A", shop="店铺1", price=100, sales=500),
            _make_product(name="商品B", shop="店铺1", price=200, sales=300),
            _make_product(name="商品C", shop="店铺1", price=150, sales=200),
        ]
        stats_map = svc._aggregate_by_shop(products)
        assert len(stats_map) == 1
        assert "店铺1" in stats_map
        stats = stats_map["店铺1"]
        assert stats.product_count == 3
        assert stats.total_sales == 1000
        assert stats.min_price == 100
        assert stats.max_price == 200

    def test_aggregate_multiple_shops(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name="A", shop="店铺1", price=100),
            _make_product(name="B", shop="店铺2", price=200),
            _make_product(name="C", shop="店铺2", price=300),
        ]
        stats_map = svc._aggregate_by_shop(products)
        assert len(stats_map) == 2
        assert stats_map["店铺1"].product_count == 1
        assert stats_map["店铺2"].product_count == 2

    def test_aggregate_ignores_unknown_shop(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name="A", shop="未知店铺", price=100),
            _make_product(name="B", shop="店铺1", price=200),
        ]
        stats_map = svc._aggregate_by_shop(products)
        assert len(stats_map) == 1
        assert "店铺1" in stats_map

    def test_aggregate_tracks_categories(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name="A", shop="店铺1", category="数码"),
            _make_product(name="B", shop="店铺1", category="家居"),
            _make_product(name="C", shop="店铺1", category="数码"),  # duplicate
        ]
        stats_map = svc._aggregate_by_shop(products)
        assert stats_map["店铺1"].category_count == 2


# ── Scoring ───────────────────────────────────────────────────


class TestScoring:
    """店铺评分逻辑测试。"""

    def test_score_range(self, session):
        svc = ShopDiscoveryService(session)
        stats = ShopStats(
            shop_name="高分店铺",
            platform="taobao",
            product_count=15,
            total_sales=5000,
            avg_price=200,
            min_price=100,
            max_price=300,
            categories={"数码", "家居", "美妆"},
        )
        score = svc._score_shop(stats)
        assert 0 <= score.score <= 100

    def test_high_product_count_scores_higher(self, session):
        svc = ShopDiscoveryService(session)
        low = ShopStats(shop_name="低", platform="taobao", product_count=2, total_sales=100, avg_price=200)
        high = ShopStats(shop_name="高", platform="taobao", product_count=20, total_sales=100, avg_price=200)
        assert svc._score_shop(high).score > svc._score_shop(low).score

    def test_high_sales_scores_higher(self, session):
        svc = ShopDiscoveryService(session)
        low = ShopStats(shop_name="低", platform="taobao", product_count=5, total_sales=50, avg_price=200)
        high = ShopStats(shop_name="高", platform="taobao", product_count=5, total_sales=5000, avg_price=200)
        assert svc._score_shop(high).sales_score > svc._score_shop(low).sales_score

    def test_mid_range_price_scores_highest(self, session):
        svc = ShopDiscoveryService(session)
        low = ShopStats(shop_name="低价", platform="taobao", product_count=5, avg_price=10)
        mid = ShopStats(shop_name="中价", platform="taobao", product_count=5, avg_price=200)
        high_p = ShopStats(shop_name="高价", platform="taobao", product_count=5, avg_price=2000)
        assert svc._score_shop(mid).price_score > svc._score_shop(low).price_score
        assert svc._score_shop(mid).price_score > svc._score_shop(high_p).price_score

    def test_zero_price_scores_zero(self, session):
        svc = ShopDiscoveryService(session)
        stats = ShopStats(shop_name="零价", platform="taobao", product_count=5, avg_price=0)
        assert svc._score_shop(stats).price_score == 0

    def test_diversity_increases_score(self, session):
        svc = ShopDiscoveryService(session)
        single = ShopStats(shop_name="单一", platform="taobao", product_count=5, avg_price=200, categories={"数码"})
        multi = ShopStats(shop_name="多元", platform="taobao", product_count=5, avg_price=200, categories={"数码", "家居", "美妆", "服饰"})
        assert svc._score_shop(multi).diversity_score > svc._score_shop(single).diversity_score


# ── Discovery flow ────────────────────────────────────────────


class TestDiscoverFromProducts:
    """discover_from_products() 完整流程测试。"""

    async def test_empty_products_returns_empty(self, session):
        svc = ShopDiscoveryService(session)
        result = await svc.discover_from_products([])
        assert result == []

    async def test_single_product_shop_filtered(self, session):
        """只有1个商品的店铺不满足最低阈值。"""
        svc = ShopDiscoveryService(session)
        products = [_make_product(name="唯一商品", shop="单店铺")]
        result = await svc.discover_from_products(products, auto_register=False)
        assert len(result) == 0  # filtered by MIN_PRODUCTS_TO_CONSIDER

    async def test_multi_product_shop_scored(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name=f"商品{i}", shop="热门店铺", sales=500, price=150)
            for i in range(5)
        ]
        result = await svc.discover_from_products(products, auto_register=False)
        assert len(result) == 1
        assert result[0].shop_name == "热门店铺"
        assert result[0].score > 0

    async def test_sorted_by_score_desc(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name=f"好商品{i}", shop="高分店铺", sales=5000, price=200)
            for i in range(5)
        ] + [
            _make_product(name=f"弱商品{i}", shop="低分店铺", sales=10, price=5)
            for i in range(3)
        ]
        result = await svc.discover_from_products(products, auto_register=False)
        assert len(result) == 2
        assert result[0].score >= result[1].score

    async def test_auto_register_high_value_shops(self, session):
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name=f"商品{i}", shop="值得注册店铺", sales=1000, price=200, category="数码")
            for i in range(5)
        ]
        result = await svc.discover_from_products(products, auto_register=True, min_score=30)

        # Verify shop was registered
        shop_svc = ShopService(session)
        all_shops = await shop_svc.list_all_shops()
        assert len(all_shops) >= 1
        registered = all_shops[0]
        assert registered.shop_name == "值得注册店铺"
        assert registered.platform == "taobao"
        assert registered.enabled is True

    async def test_no_register_below_threshold(self, session):
        """低于阈值的店铺不注册。"""
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name=f"商品{i}", shop="低分店铺", sales=1, price=1)
            for i in range(3)
        ]
        await svc.discover_from_products(products, auto_register=True, min_score=90)
        shop_svc = ShopService(session)
        all_shops = await shop_svc.list_all_shops()
        assert len(all_shops) == 0

    async def test_no_duplicate_registration(self, session):
        """已存在的店铺不重复注册。"""
        svc = ShopDiscoveryService(session)
        products = [
            _make_product(name=f"商品{i}", shop="已存在店铺", sales=1000, price=200)
            for i in range(5)
        ]
        # Run discovery twice
        await svc.discover_from_products(products, auto_register=True, min_score=30)
        await svc.discover_from_products(products, auto_register=True, min_score=30)

        shop_svc = ShopService(session)
        all_shops = await shop_svc.list_all_shops()
        # Should only have 1 shop (not duplicated)
        assert len(all_shops) == 1


# ── Utility methods ───────────────────────────────────────────


class TestUtilities:
    """工具方法测试。"""

    def test_generate_shop_id_deterministic(self):
        id1 = ShopDiscoveryService._generate_shop_id("测试店铺", "taobao")
        id2 = ShopDiscoveryService._generate_shop_id("测试店铺", "taobao")
        assert id1 == id2
        assert len(id1) == 16

    def test_generate_shop_id_different_platforms(self):
        id1 = ShopDiscoveryService._generate_shop_id("同店", "taobao")
        id2 = ShopDiscoveryService._generate_shop_id("同店", "tmall")
        assert id1 != id2

    def test_score_to_priority(self):
        assert ShopDiscoveryService._score_to_priority(80) == 3
        assert ShopDiscoveryService._score_to_priority(60) == 2
        assert ShopDiscoveryService._score_to_priority(30) == 1

    def test_primary_category(self):
        stats = ShopStats(shop_name="test", platform="taobao", categories={"数码", "家居"})
        cat = ShopDiscoveryService._primary_category(stats)
        assert cat in ("数码", "家居")

    def test_primary_category_empty(self):
        stats = ShopStats(shop_name="test", platform="taobao")
        assert ShopDiscoveryService._primary_category(stats) is None


# ── Pipeline integration ──────────────────────────────────────


class TestPipelineIntegration:
    """Pipeline Step 11c 集成测试。"""

    def test_step_11c_exists_in_jobs(self):
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "Step 11c" in source or "shop_discovery" in source.lower()

    def test_step_11c_uses_shop_discovery_service(self):
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "ShopDiscoveryService" in source

    def test_step_11c_auto_register(self):
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "auto_register" in source
