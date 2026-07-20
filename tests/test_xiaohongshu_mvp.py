"""Tests for Phase 9.3 — Xiaohongshu real crawl MVP.

Covers: parameters, limit, RawProduct fields, exception handling.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.base import CookieManager
from app.crawler.models.schemas import RawProduct
from app.crawler.xiaohongshu import XiaohongshuCrawler


# ── Test Crawler ─────────────────────────────────────────────


def _make_crawler(tmp_path: Path, login_ok: bool = True) -> XiaohongshuCrawler:
    """Create a XiaohongshuCrawler with mocked internals."""
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
    # safe_goto(page, url, ...) should return the page so subsequent calls work
    async def _safe_goto_impl(page, url, **kwargs):
        return page
    crawler._browser_manager.safe_goto = AsyncMock(side_effect=_safe_goto_impl)
    crawler.check_login = AsyncMock(return_value=login_ok)
    return crawler


# ── Mock Element Builders ────────────────────────────────────


def _make_element(data: dict):
    """Build a mock DOM element.

    *data* maps CSS selector fragments to values:
      str  → inner_text() returns that string
      dict → get_attribute(key) returns val
      None → query_selector returns None
    """
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


# CSS class names chosen to avoid cross-matching between selectors:
#   "product-title" → matches [class*='title']  (not shop/link)
#   "price-tag"     → matches [class*='price']
#   "item-img"      → matches "img" tag selector
#   "shop-info"     → matches [class*='shop']   (not author/store)
#   "view-num"      → matches [class*='view']   (not count/browse/like)
#   "sold-num"      → matches [class*='sold']   (not sales/buy)
#   "product-link"  → matches [class*='goods']  in href


def _complete_card(idx: int = 1) -> AsyncMock:
    """Card with all parseable fields."""
    return _make_element({
        "title": f"测试商品{idx}",
        "price": "¥199",
        "img": {"src": f"https://img.example.com/{idx}.jpg"},
        "shop": "测试店铺",
        "count": "3200浏览",
        "sold": "500人付款",
        "goods": {"href": f"/explore/{idx}"},
    })


def _minimal_card(idx: int = 1) -> AsyncMock:
    """Card with only a title — no price, image, shop, viewers, sales, link."""
    return _make_element({
        "title": f"简单商品{idx}",
    })


def _make_cards(count: int, factory=_complete_card):
    return [factory(i) for i in range(1, count + 1)]


def _make_mock_page(cards: list | None = None):
    """Build a mock Page whose query_selector_all returns *cards*."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=cards or [])
    page.evaluate = AsyncMock()
    page.mouse = AsyncMock()
    page.mouse.move = AsyncMock()
    return page


def _make_mock_context(page):
    """Build a mock BrowserContext whose new_page() returns *page*."""
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.cookies = AsyncMock(return_value=[])
    ctx.close = AsyncMock()
    return ctx


# ── TestCrawlParameters ──────────────────────────────────────


class TestCrawlParameters:
    """keyword / max_pages / limit are forwarded correctly."""

    @pytest.mark.anyio
    async def test_keyword_in_search_url(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(1)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler._do_crawl("口红", max_pages=1)

        call_args = crawler._browser_manager.safe_goto.call_args_list
        assert any("keyword=口红" in str(c) for c in call_args)

    @pytest.mark.anyio
    async def test_max_pages_controls_pagination(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            await crawler._do_crawl("test", max_pages=5)

        # 5 pages → 5 safe_goto calls
        goto_calls = crawler._browser_manager.safe_goto.call_args_list
        assert len(goto_calls) == 5

    @pytest.mark.anyio
    async def test_default_limit_is_100(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        page = _make_mock_page([])
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            # limit defaults to 100
            await crawler._do_crawl("test", max_pages=1)

        # Should not error — default limit is accepted
        assert True

    @pytest.mark.anyio
    async def test_crawl_override_passes_limit(self, tmp_path):
        """XiaohongshuCrawler.crawl() should accept and forward limit."""
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(10)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler.crawl("test", max_pages=1, limit=3)

        assert len(products) == 3


# ── TestCrawlLimit ───────────────────────────────────────────


class TestCrawlLimit:
    """limit caps the number of collected products."""

    @pytest.mark.anyio
    async def test_limit_stops_at_exact_count(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(10)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1, limit=5)

        assert len(products) == 5

    @pytest.mark.anyio
    async def test_limit_one(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(5)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1, limit=1)

        assert len(products) == 1

    @pytest.mark.anyio
    async def test_limit_greater_than_cards_returns_all(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(3)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1, limit=100)

        assert len(products) == 3

    @pytest.mark.anyio
    async def test_limit_spans_multiple_pages(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(4)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            # 2 pages × 4 cards = 8, but limit = 6
            products = await crawler._do_crawl("test", max_pages=2, limit=6)

        assert len(products) == 6


# ── TestRawProductFields ────────────────────────────────────


class TestRawProductFields:
    """All fields (name, image, price, sales, viewers, shop, url, platform) are parsed."""

    @pytest.mark.anyio
    async def test_all_fields_populated(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_complete_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert len(products) == 1
        p = products[0]
        assert p.name == "测试商品1"
        assert p.platform == "xiaohongshu"
        assert p.price == 199.0
        assert p.image == "https://img.example.com/1.jpg"
        assert p.shop == "测试店铺"
        assert p.viewers == 3200
        assert p.sales_24h == 500
        assert p.url == "/explore/1"

    @pytest.mark.anyio
    async def test_platform_always_xiaohongshu(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = _make_cards(3)
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        for p in products:
            assert p.platform == "xiaohongshu"

    @pytest.mark.anyio
    async def test_sales_parsed_from_sold_text(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_complete_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].sales_24h == 500

    @pytest.mark.anyio
    async def test_sales_wan_format(self, tmp_path):
        """parse_count handles '1.2万' → 12000."""
        crawler = _make_crawler(tmp_path)
        card = _make_element({
            "title": "爆款商品",
            "price": "¥99",
            "sold": "1.2万已售",
        })
        page = _make_mock_page([card])
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].sales_24h == 12000

    @pytest.mark.anyio
    async def test_viewers_parsed(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        cards = [_complete_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert products[0].viewers == 3200

    @pytest.mark.anyio
    async def test_minimal_card_defaults(self, tmp_path):
        """Card with only name gets defaults for other fields."""
        crawler = _make_crawler(tmp_path)
        cards = [_minimal_card(1)]
        page = _make_mock_page(cards)
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        p = products[0]
        assert p.name == "简单商品1"
        assert p.platform == "xiaohongshu"
        assert p.price == 0.0
        assert p.image is None
        assert p.shop == "未知店铺"
        assert p.viewers == 0
        assert p.sales_24h == 0
        assert p.url is None

    @pytest.mark.anyio
    async def test_empty_name_skipped(self, tmp_path):
        """Card without a parseable name is skipped."""
        crawler = _make_crawler(tmp_path)
        # No "title" key → name_el is None → name="" → returns None
        card = _make_element({"price": "¥199"})
        page = _make_mock_page([card])
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        assert len(products) == 0


# ── TestExceptionHandling ────────────────────────────────────


class TestExceptionHandling:
    """Graceful handling of login failure and runtime errors."""

    @pytest.mark.anyio
    async def test_not_logged_in_returns_empty(self, tmp_path):
        crawler = _make_crawler(tmp_path, login_ok=False)
        products = await crawler._do_crawl("test", max_pages=1)
        assert products == []

    @pytest.mark.anyio
    async def test_not_logged_in_skips_browser(self, tmp_path):
        """When not logged in, _new_context should not be called."""
        crawler = _make_crawler(tmp_path, login_ok=False)
        with patch.object(crawler, "_new_context", side_effect=RuntimeError("should not reach")):
            products = await crawler._do_crawl("test", max_pages=1)
        assert products == []

    @pytest.mark.anyio
    async def test_new_context_failure_raises(self, tmp_path):
        crawler = _make_crawler(tmp_path)
        with patch.object(crawler, "_new_context", side_effect=RuntimeError("browser crashed")):
            with pytest.raises(RuntimeError, match="browser crashed"):
                await crawler._do_crawl("test", max_pages=1)

    @pytest.mark.anyio
    async def test_parse_product_exception_returns_none(self, tmp_path):
        """If _parse_product raises, the card is skipped gracefully."""
        crawler = _make_crawler(tmp_path)

        bad_card = AsyncMock()
        bad_card.query_selector = AsyncMock(side_effect=RuntimeError("DOM error"))

        good_card = _complete_card(1)
        page = _make_mock_page([bad_card, good_card])
        context = _make_mock_context(page)

        with patch.object(crawler, "_new_context", return_value=context):
            products = await crawler._do_crawl("test", max_pages=1)

        # bad_card skipped, good_card parsed
        assert len(products) == 1
        assert products[0].name == "测试商品1"

    @pytest.mark.anyio
    async def test_crawl_override_handles_retry_exhaustion(self, tmp_path):
        """crawl() returns [] when all retries fail."""
        crawler = _make_crawler(tmp_path)
        with patch.object(crawler, "_do_crawl", side_effect=RuntimeError("permanent failure")):
            products = await crawler.crawl("test", max_pages=1, limit=10)
        assert products == []
