"""Tests for Phase 16 Task 2: 1688 real supply chain search."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.crawler.alibaba_1688 import Alibaba1688Crawler
from app.crawler.alibaba_1688 import SupplierProduct as CrawlerSupplierProduct
from app.crawler.base import VALID_PLATFORMS
from app.crawler.models.schemas import RawProduct


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


