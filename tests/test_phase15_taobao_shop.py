"""Tests for Phase 15: Real TaobaoCrawler + Shop Registry enhancements."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.database.base import Base
from app.services.shop_service import ShopService
from app.crawler.taobao import TaobaoCrawler
from app.crawler.models.schemas import RawProduct


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


# ── TaobaoCrawler new methods ─────────────────────────────────


class TestTaobaoCrawlerProductionMethods:
    """TaobaoCrawler 生产级方法测试。"""

    def test_has_crawl_method(self):
        """TaobaoCrawler 应有 crawl 方法（覆盖基类）。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "crawl")
        assert hasattr(crawler, "_do_crawl")

    def test_has_crawl_shop_method(self):
        """TaobaoCrawler 应有 crawl_shop 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "crawl_shop")
        assert callable(crawler.crawl_shop)

    def test_has_login_method(self):
        """TaobaoCrawler 应有 login 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "login")

    def test_has_check_login_method(self):
        """TaobaoCrawler 应有 check_login 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "check_login")

    def test_search_url(self):
        """SEARCH_URL 应指向淘宝搜索。"""
        assert "s.taobao.com" in TaobaoCrawler.SEARCH_URL

    def test_sort_params_defined(self):
        """应定义排序参数映射。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "_sort_params")
        assert "general" in crawler._sort_params
        assert "sales" in crawler._sort_params

    def test_card_selector_defined(self):
        """应定义商品卡片选择器。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "_card_selector")
        assert len(crawler._card_selector) > 0


class TestTaobaoCrawlerCrawlShop:
    """crawl_shop 方法单元测试。"""

    async def test_crawl_shop_returns_empty_when_not_logged_in(self):
        """未登录时 crawl_shop 应返回空列表。"""
        crawler = TaobaoCrawler()
        crawler.check_login = AsyncMock(return_value=False)
        result = await crawler.crawl_shop(
            shop_url="https://shop123.taobao.com",
            shop_name="测试店铺",
        )
        assert result == []

    async def test_crawl_shop_signature(self):
        """crawl_shop 应接受 shop_url, shop_name, max_pages, limit 参数。"""
        import inspect
        sig = inspect.signature(TaobaoCrawler.crawl_shop)
        params = list(sig.parameters.keys())
        assert "shop_url" in params
        assert "shop_name" in params
        assert "max_pages" in params
        assert "limit" in params


class TestTaobaoCrawlerDoCrawl:
    """_do_crawl 方法测试。"""

    async def test_do_crawl_returns_empty_when_not_logged_in(self):
        """未登录时 _do_crawl 应返回空列表。"""
        crawler = TaobaoCrawler()
        crawler.check_login = AsyncMock(return_value=False)
        result = await crawler._do_crawl(keyword="蓝牙耳机")
        assert result == []


# ── ShopService enhancements ──────────────────────────────────


class TestBatchMarkScanned:
    """batch_mark_scanned() 批量标记扫描。"""

    async def test_batch_mark_empty_list(self, session):
        svc = ShopService(session)
        count = await svc.batch_mark_scanned([])
        assert count == 0

    async def test_batch_mark_multiple_shops(self, session):
        svc = ShopService(session)
        s1 = await svc.create_shop(platform="taobao", shop_id="bm1", shop_name="店1")
        s2 = await svc.create_shop(platform="taobao", shop_id="bm2", shop_name="店2")
        s3 = await svc.create_shop(platform="taobao", shop_id="bm3", shop_name="店3")

        scan_time = datetime(2026, 7, 21, 10, 0, 0)
        count = await svc.batch_mark_scanned([s1.id, s2.id, s3.id], scan_time=scan_time)
        assert count == 3

        # Verify all marked
        for sid in [s1.id, s2.id, s3.id]:
            shop = await svc.get_shop(sid)
            assert shop.last_scan_at == scan_time

    async def test_batch_mark_default_time(self, session):
        svc = ShopService(session)
        s1 = await svc.create_shop(platform="taobao", shop_id="bmd1", shop_name="默认时间")
        count = await svc.batch_mark_scanned([s1.id])
        assert count == 1
        shop = await svc.get_shop(s1.id)
        assert shop.last_scan_at is not None


class TestRegisterOrUpdate:
    """register_or_update() upsert 逻辑。"""

    async def test_create_new_shop(self, session):
        svc = ShopService(session)
        shop = await svc.register_or_update(
            platform="taobao",
            shop_id="new_001",
            shop_name="新店铺",
            shop_url="https://shop001.taobao.com",
            category="数码",
        )
        assert shop.id is not None
        assert shop.shop_name == "新店铺"
        assert shop.shop_url == "https://shop001.taobao.com"

    async def test_update_existing_shop(self, session):
        svc = ShopService(session)
        # Create first
        await svc.register_or_update(
            platform="taobao", shop_id="upd_001", shop_name="原名"
        )
        # Update via upsert
        shop = await svc.register_or_update(
            platform="taobao",
            shop_id="upd_001",
            shop_name="新名",
            fans=5000,
        )
        assert shop.shop_name == "新名"
        assert shop.fans == 5000

    async def test_upsert_different_platforms(self, session):
        """不同平台应各自独立管理店铺。"""
        svc = ShopService(session)
        s1 = await svc.register_or_update(
            platform="taobao", shop_id="tb_001", shop_name="淘宝"  # noqa: E501
        )
        s2 = await svc.register_or_update(
            platform="tmall", shop_id="tm_001", shop_name="天猫"  # noqa: E501
        )
        assert s1.id != s2.id
        assert s1.platform == "taobao"
        assert s2.platform == "tmall"


class TestGetShopsNeedingScan:
    """get_shops_needing_scan() 扫描策略测试。"""

    async def test_never_scanned_shops_need_scan(self, session):
        svc = ShopService(session)
        await svc.create_shop(
            platform="taobao", shop_id="ns1", shop_name="从未扫描",
            monitor_strategy="daily"
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 1
        assert needing[0].shop_id == "ns1"

    async def test_recently_scanned_shop_no_need(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="taobao", shop_id="rs1", shop_name="刚扫描",
            monitor_strategy="daily"
        )
        await svc.mark_scanned(shop.id, scan_time=datetime.now())
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 0

    async def test_stale_scan_needs_rescan(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="taobao", shop_id="st1", shop_name="过期扫描",
            monitor_strategy="daily"
        )
        # Mark scanned 2 days ago
        await svc.mark_scanned(
            shop.id, scan_time=datetime.now() - timedelta(days=2)
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 1

    async def test_manual_strategy_never_auto_scan(self, session):
        svc = ShopService(session)
        await svc.create_shop(
            platform="taobao", shop_id="man1", shop_name="手动策略",
            monitor_strategy="manual"
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 0

    async def test_hourly_strategy_threshold(self, session):
        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="taobao", shop_id="hr1", shop_name="小时策略",
            monitor_strategy="hourly"
        )
        # Scanned 30 min ago — should NOT need scan
        await svc.mark_scanned(
            shop.id, scan_time=datetime.now() - timedelta(minutes=30)
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 0

        # Scanned 2 hours ago — should need scan
        await svc.mark_scanned(
            shop.id, scan_time=datetime.now() - timedelta(hours=2)
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 1

    async def test_disabled_shops_excluded(self, session):
        svc = ShopService(session)
        await svc.create_shop(
            platform="taobao", shop_id="dis1", shop_name="禁用",
            enabled=False, monitor_strategy="daily"
        )
        needing = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing) == 0

    async def test_platform_filter(self, session):
        svc = ShopService(session)
        await svc.create_shop(
            platform="taobao", shop_id="pf1", shop_name="淘宝",
            monitor_strategy="daily"
        )
        await svc.create_shop(
            platform="tmall", shop_id="pf2", shop_name="天猫",
            monitor_strategy="daily"
        )
        needing_taobao = await svc.get_shops_needing_scan(platform="taobao")
        assert len(needing_taobao) == 1
        assert needing_taobao[0].platform == "taobao"


class TestGetShopStats:
    """get_shop_stats() 统计测试。"""

    async def test_stats_empty(self, session):
        svc = ShopService(session)
        stats = await svc.get_shop_stats()
        assert stats["total"] == 0
        assert stats["enabled"] == 0

    async def test_stats_with_shops(self, session):
        svc = ShopService(session)
        await svc.create_shop(platform="taobao", shop_id="st1", shop_name="淘宝1", enabled=True)
        await svc.create_shop(platform="taobao", shop_id="st2", shop_name="淘宝2", enabled=True)
        await svc.create_shop(platform="tmall", shop_id="st3", shop_name="天猫1", enabled=False)
        stats = await svc.get_shop_stats()
        assert stats["total"] == 3
        assert stats["enabled"] == 2
        assert stats["by_platform"]["taobao"] == 2
        assert stats["by_platform"]["tmall"] == 1


# ── Pipeline integration ──────────────────────────────────────


class TestPipelineShopScanStep:
    """Pipeline Step 11b 店铺扫描集成测试。"""

    def test_step_11b_exists_in_jobs(self):
        """jobs.py 应包含 Step 11b 店铺扫描逻辑。"""
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "Step 11b" in source or "shop_scan" in source.lower()

    def test_shop_scan_uses_taobao_crawler(self):
        """店铺扫描步骤应使用 TaobaoCrawler。"""
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "TaobaoCrawler" in source or "crawl_shop" in source

    def test_shop_scan_calls_batch_mark_scanned(self):
        """店铺扫描后应调用 batch_mark_scanned。"""
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs.daily_crawl_job)
        assert "batch_mark_scanned" in source


# ── TaobaoCrawler cookie persistence ──────────────────────────


class TestTaobaoCookiePersistence:
    """Cookie 持久化相关测试。"""

    def test_has_save_cookies(self):
        """TaobaoCrawler 继承 save_cookies 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "save_cookies")

    def test_has_load_cookies(self):
        """TaobaoCrawler 继承 load_cookies 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "load_cookies")

    def test_has_has_cookies(self):
        """TaobaoCrawler 继承 has_cookies 方法。"""
        crawler = TaobaoCrawler()
        assert hasattr(crawler, "has_cookies")
