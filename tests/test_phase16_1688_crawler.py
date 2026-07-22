"""Tests for Phase 16 Task 2: 1688 real supply chain search."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.crawler.alibaba_1688 import Alibaba1688Crawler
from app.crawler.alibaba_1688 import SupplierProduct as CrawlerSupplierProduct
from app.crawler.base import VALID_PLATFORMS
from app.crawler.models.schemas import RawProduct
from app.services.supply_chain.provider import SupplyChainProvider, SupplierProduct


# ── Platform registration ─────────────────────────────────────


class TestPlatformRegistration:
    """1688 平台注册测试。"""

    def test_1688_in_valid_platforms(self):
        assert "1688" in VALID_PLATFORMS

    def test_cookie_manager_accepts_1688(self, tmp_path):
        from app.crawler.base import CookieManager
        manager = CookieManager(tmp_path)
        path = manager.get_cookie_path("1688")
        assert path.name == "1688.json"


# ── Alibaba1688Crawler ────────────────────────────────────────


class TestAlibaba1688Crawler:
    """Alibaba1688Crawler 基础测试。"""

    def test_platform_attribute(self):
        crawler = Alibaba1688Crawler()
        assert crawler.PLATFORM == "1688"

    def test_base_url(self):
        assert "1688.com" in Alibaba1688Crawler.BASE_URL

    def test_search_url(self):
        assert "1688.com" in Alibaba1688Crawler.SEARCH_URL

    def test_has_search_suppliers(self):
        crawler = Alibaba1688Crawler()
        assert hasattr(crawler, "search_suppliers")
        assert callable(crawler.search_suppliers)

    def test_has_check_login(self):
        crawler = Alibaba1688Crawler()
        assert hasattr(crawler, "check_login")

    def test_has_login(self):
        crawler = Alibaba1688Crawler()
        assert hasattr(crawler, "login")

    async def test_search_returns_empty_when_not_logged_in(self):
        crawler = Alibaba1688Crawler()
        crawler.check_login = AsyncMock(return_value=False)
        results = await crawler.search_suppliers("蓝牙耳机")
        assert results == []


# ── SupplierProduct ───────────────────────────────────────────


class TestSupplierProduct:
    """SupplierProduct 数据类测试。"""

    def test_to_raw_product(self):
        sp = CrawlerSupplierProduct(
            product_id="test_001",
            title="测试商品",
            price=29.9,
            supplier_name="测试供应商",
        )
        raw = sp.to_raw_product()
        assert isinstance(raw, RawProduct)
        assert raw.name == "测试商品"
        assert raw.platform == "1688"
        assert raw.shop == "测试供应商"
        assert raw.price == 29.9


# ── SupplyChainProvider ───────────────────────────────────────


class TestSupplyChainProvider:
    """SupplyChainProvider 数据源抽象测试。"""

    async def test_default_mock_mode(self):
        """默认使用 mock 数据。"""
        provider = SupplyChainProvider()
        assert provider._use_real_crawler is False
        assert provider._use_mock_fallback is True

    async def test_mock_search_returns_results(self):
        """Mock 模式应返回结果。"""
        provider = SupplyChainProvider()
        results = await provider.search("蓝牙耳机")
        assert len(results) > 0
        assert all(isinstance(r, SupplierProduct) for r in results)

    async def test_mock_search_has_correct_fields(self):
        """Mock 结果应包含完整字段。"""
        provider = SupplyChainProvider()
        results = await provider.search("蓝牙耳机")
        assert len(results) > 0
        r = results[0]
        assert r.product_id
        assert r.title
        assert r.price > 0
        assert r.supplier_name

    async def test_mock_fallback_full_catalog(self):
        """无关键词匹配时应返回全目录。"""
        provider = SupplyChainProvider()
        results = await provider.search("完全不存在的关键词XYZABC")
        assert len(results) > 0  # Falls back to full catalog

    async def test_cache_works(self):
        """缓存应生效。"""
        provider = SupplyChainProvider()
        r1 = await provider.search("蓝牙耳机")
        r2 = await provider.search("蓝牙耳机")
        assert r1 == r2  # Same results from cache

    async def test_clear_cache(self):
        """清除缓存后应重新查询。"""
        provider = SupplyChainProvider()
        await provider.search("蓝牙耳机")
        assert len(provider._cache) > 0
        provider.clear_cache()
        assert len(provider._cache) == 0

    async def test_real_crawler_mode_can_be_enabled(self):
        """可以启用真实爬虫模式。"""
        provider = SupplyChainProvider(use_real_crawler=True)
        assert provider._use_real_crawler is True

    async def test_limit_parameter(self):
        """limit 参数应限制返回数量。"""
        provider = SupplyChainProvider()
        results = await provider.search("蓝牙耳机", limit=2)
        assert len(results) <= 2

    async def test_close(self):
        """close 应清理资源。"""
        provider = SupplyChainProvider()
        await provider.close()  # Should not raise


# ── SupplyChainMatcher integration ────────────────────────────


class TestMatcherWithProvider:
    """SupplyChainMatcher + Provider 集成测试。"""

    async def test_matcher_accepts_provider(self):
        """SupplyChainMatcher 应接受自定义 provider。"""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from app.database.base import Base
        import app.models  # noqa

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            provider = SupplyChainProvider()
            matcher = SupplyChainMatcher(session, provider=provider)
            assert matcher._provider is provider
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
