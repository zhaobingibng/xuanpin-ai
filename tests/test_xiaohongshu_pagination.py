"""Tests for Phase 9.7.5 — Xiaohongshu pagination, sort, and enhanced fields.

Covers: multi-page crawl, sort parameter, favorites/comments/publish_time parsing.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.base import CookieManager
from app.crawler.models.schemas import RawProduct
from app.crawler.xiaohongshu import XiaohongshuCrawler, SORT_PARAMS


# ── Helpers ────────────────────────────────────────────────────


def _make_crawler(tmp_path: Path, login_ok: bool = True) -> XiaohongshuCrawler:
    crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
    crawler.PLATFORM = "xiaohongshu"
    crawler.BASE_URL = "https://www.xiaohongshu.com"
    crawler.SEARCH_URL = "https://www.xiaohongshu.com/search_result"
    crawler._settings = MagicMock()
    crawler._settings.crawler_retry = 3
    crawler._settings.crawler_retry_times = 3
    crawler._settings.crawler_retry_delay = 0
    crawler._settings.login_check_timeout = 15
    crawler._cookie_manager = CookieManager(tmp_path)
    crawler._playwright = None
    crawler._browser = None
    crawler._browser_manager = AsyncMock()
    crawler.check_login = AsyncMock(return_value=login_ok)
    return crawler


def _make_element(data: dict):
    el = AsyncMock()

    async def _qs(selector):
        for key, val in data.items():
            if key in selector:
                if val is None:
                    return None
                child = AsyncMock()
                if isinstance(val, str):
                    child.inner_text = AsyncMock(return_value=val)
                elif isinstance(val, dict):
                    async def _ga(name, _v=val):
                        return _v.get(name)
                    child.get_attribute = _ga
                return child
        return None

    el.query_selector = _qs
    return el


def _enhanced_card(idx: int = 1) -> AsyncMock:
    """Card with all enhanced fields including favorites, comments, publish_time."""
    return _make_element({
        "title": f"增强商品{idx}",
        "price": "¥299",
        "img": {"src": f"https://img.example.com/{idx}.jpg"},
        "shop": "测试店铺",
        "count": "5000浏览",
        "sold": "800人付款",
        "goods": {"href": f"/explore/{idx}"},
        "collect": "1200收藏",
        "comment": "350评论",
        "time": "2026-07-15",
    })


def _basic_card(idx: int = 1) -> AsyncMock:
    """Card with basic fields only."""
    return _make_element({
        "title": f"基础商品{idx}",
        "price": "¥99",
        "sold": "100人付款",
    })


def _make_mock_page(cards: list | None = None):
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=cards or [])
    page.evaluate = AsyncMock()
    page.mouse = AsyncMock()
    page.mouse.move = AsyncMock()
    return page


def _make_mock_context(page):
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.cookies = AsyncMock(return_value=[])
    ctx.close = AsyncMock()
    return ctx


# ── TestPagination ─────────────────────────────────────────────


class TestPagination:
    """Multi-page crawl with page_limit control."""

    @pytest.mark.anyio
    async def test_multi_page_collects_all(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_basic_card(i) for i in range(1, 4)]  # 3 per page
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=3, limit=100)

        assert len(products) == 9  # 3 pages × 3 cards

    @pytest.mark.anyio
    async def test_page_limit_stops_early(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_basic_card(i) for i in range(1, 6)]  # 5 per page
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=5, limit=7)

        assert len(products) == 7

    @pytest.mark.anyio
    async def test_single_page(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_basic_card(1), _basic_card(2)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1, limit=100)

        assert len(products) == 2

    @pytest.mark.anyio
    async def test_empty_page_stops_gracefully(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=3, limit=100)

        assert len(products) == 0


# ── TestSortParameter ──────────────────────────────────────────


class TestSortParameter:
    """crawl_sort parameter controls URL sort query."""

    @pytest.mark.anyio
    async def test_default_sort_is_general(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler._do_crawl("test", max_pages=1)

        call_args = crawler._browser_manager.safe_goto.call_args
        url = call_args[0][1]  # second positional arg
        assert "sort=general" in url

    @pytest.mark.anyio
    async def test_sales_sort(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler._do_crawl("test", max_pages=1, crawl_sort="sales")

        call_args = crawler._browser_manager.safe_goto.call_args
        url = call_args[0][1]
        assert "sort=sales" in url

    @pytest.mark.anyio
    async def test_latest_sort(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler._do_crawl("test", max_pages=1, crawl_sort="latest")

        call_args = crawler._browser_manager.safe_goto.call_args
        url = call_args[0][1]
        assert "sort=time" in url

    def test_sort_params_mapping(self):
        assert SORT_PARAMS["general"] == "general"
        assert SORT_PARAMS["sales"] == "sales"
        assert SORT_PARAMS["latest"] == "time"

    @pytest.mark.anyio
    async def test_crawl_passes_sort_to_do_crawl(self, tmp_path):
        """crawl() public method forwards crawl_sort."""
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler.crawl("test", max_pages=1, crawl_sort="sales")

        url = crawler._browser_manager.safe_goto.call_args[0][1]
        assert "sort=sales" in url


# ── TestEnhancedFields ─────────────────────────────────────────


class TestEnhancedFields:
    """Parse favorites, comments, publish_time from product cards."""

    @pytest.mark.anyio
    async def test_favorites_parsed(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_enhanced_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].favorites == 1200

    @pytest.mark.anyio
    async def test_comments_parsed(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_enhanced_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].comments == 350

    @pytest.mark.anyio
    async def test_publish_time_parsed(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_enhanced_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].publish_time == "2026-07-15"

    @pytest.mark.anyio
    async def test_basic_card_defaults_enhanced_fields(self, tmp_path):
        """Cards without enhanced fields get defaults."""
        crawler = _make_crawler(tmp_path)
        cards = [_basic_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        p = products[0]
        assert p.favorites == 0
        assert p.comments == 0
        assert p.publish_time is None

    @pytest.mark.anyio
    async def test_enhanced_card_all_fields(self, tmp_path):
        """All fields populated correctly."""
        crawler = _make_crawler(tmp_path)
        cards = [_enhanced_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)
        crawler._browser_manager.safe_goto = AsyncMock(return_value=page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        p = products[0]
        assert p.name == "增强商品1"
        assert p.platform == "xiaohongshu"
        assert p.price == 299.0
        assert p.shop == "测试店铺"
        assert p.viewers == 5000
        assert p.sales_24h == 800
        assert p.favorites == 1200
        assert p.comments == 350
        assert p.publish_time == "2026-07-15"


# ── TestRawProductFields ──────────────────────────────────────


class TestRawProductSchema:
    """RawProduct dataclass has new fields."""

    def test_favorites_field_exists(self):
        p = RawProduct(name="test", platform="xhs", shop="s", price=0.0)
        assert p.favorites == 0

    def test_comments_field_exists(self):
        p = RawProduct(name="test", platform="xhs", shop="s", price=0.0)
        assert p.comments == 0

    def test_publish_time_field_exists(self):
        p = RawProduct(name="test", platform="xhs", shop="s", price=0.0)
        assert p.publish_time is None

    def test_custom_values(self):
        p = RawProduct(
            name="test", platform="xhs", shop="s", price=99.0,
            favorites=500, comments=100, publish_time="2026-01-01",
        )
        assert p.favorites == 500
        assert p.comments == 100
        assert p.publish_time == "2026-01-01"
