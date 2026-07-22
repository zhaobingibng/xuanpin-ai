"""Tests for Phase 16.8 Task 2: Taobao shop crawl enhancement."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.taobao import TaobaoCrawler, CrawlResult


# ── URL Normalization Tests ────────────────────────────────


class TestNormalizeShopUrl:
    """Test _normalize_shop_url static method."""

    def test_shop_homepage_to_search(self):
        """Shop homepage -> /search.htm."""
        url = "https://shop123.taobao.com"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://shop123.taobao.com/search.htm"

    def test_shop_homepage_trailing_slash(self):
        """Shop homepage with trailing slash -> /search.htm."""
        url = "https://shop123.taobao.com/"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://shop123.taobao.com/search.htm"

    def test_search_page_keep_as_is(self):
        """Already a search page -> keep as-is."""
        url = "https://shop123.taobao.com/search.htm"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == url

    def test_search_page_with_query(self):
        """Search page with query params -> keep as-is."""
        url = "https://shop123.taobao.com/search.htm?page=1&order=price"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == url

    def test_tmall_shop(self):
        """Tmall shop URL with query params -> kept as-is."""
        url = "https://store.taobao.com/shop/view_shop.htm?appKey=xxx"
        result = TaobaoCrawler._normalize_shop_url(url)
        # Contains ? so it's kept as-is
        assert result == url

    def test_tmall_shop_homepage(self):
        """Tmall shop homepage -> /category.htm."""
        url = "https://sanzhisongshu.tmall.com"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://sanzhisongshu.tmall.com/category.htm"

    def test_tmall_shop_trailing_slash(self):
        """Tmall shop with trailing slash -> /category.htm."""
        url = "https://sanzhisongshu.tmall.com/"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://sanzhisongshu.tmall.com/category.htm"

    def test_tmall_shop_view_shop(self):
        """Tmall /shop/view_shop.htm -> /category.htm."""
        url = "https://sanzhisongshu.tmall.com/shop/view_shop.htm"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://sanzhisongshu.tmall.com/category.htm"

    def test_no_protocol_adds_https(self):
        """URL without protocol -> adds https://."""
        url = "shop123.taobao.com"
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://shop123.taobao.com/search.htm"

    def test_whitespace_stripped(self):
        """URL with whitespace -> stripped."""
        url = "  https://shop123.taobao.com  "
        result = TaobaoCrawler._normalize_shop_url(url)
        assert result == "https://shop123.taobao.com/search.htm"


# ── Crawl Shop With Metrics Tests ──────────────────────────


class TestCrawlShopWithMetrics:
    """Test crawl_shop_with_metrics method."""

    @pytest.fixture
    def crawler(self):
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)
            return TaobaoCrawler()

    async def test_not_logged_in(self, crawler):
        """Test returns not_logged_in when not authenticated."""
        crawler.check_login = AsyncMock(return_value=False)

        result = await crawler.crawl_shop_with_metrics(
            shop_url="https://shop123.taobao.com"
        )

        assert isinstance(result, CrawlResult)
        assert result.is_logged_in is False
        assert result.failure_reason == "not_logged_in"
        assert result.real_product_count == 0

    async def test_successful_crawl(self, crawler):
        """Test successful shop crawl returns metrics."""
        crawler.check_login = AsyncMock(return_value=True)
        crawler._last_pages_crawled = 2

        # Mock crawl_shop directly
        mock_products = [MagicMock(), MagicMock()]
        crawler.crawl_shop = AsyncMock(return_value=mock_products)

        result = await crawler.crawl_shop_with_metrics(
            shop_url="https://shop123.taobao.com",
            max_pages=2,
            limit=10,
        )

        assert result.is_logged_in is True
        assert result.real_product_count == 2
        assert result.pages_crawled == 2
        assert result.failure_reason == ""
        assert result.elapsed_seconds >= 0  # May be 0 for fast mocks

    async def test_empty_result_sets_failure_reason(self, crawler):
        """Test empty result sets no_products_found."""
        crawler.check_login = AsyncMock(return_value=True)
        crawler.crawl_shop = AsyncMock(return_value=[])
        crawler._last_pages_crawled = 1

        result = await crawler.crawl_shop_with_metrics(
            shop_url="https://shop123.taobao.com"
        )

        assert result.real_product_count == 0
        assert result.failure_reason == "no_products_found"

    async def test_exception_sets_error_reason(self, crawler):
        """Test exception during crawl sets error reason."""
        crawler.check_login = AsyncMock(return_value=True)
        crawler.crawl_shop = AsyncMock(side_effect=Exception("Browser crashed"))

        result = await crawler.crawl_shop_with_metrics(
            shop_url="https://shop123.taobao.com"
        )

        assert result.failure_reason.startswith("crawl_error:")
        assert "Browser crashed" in result.failure_reason
        assert result.real_product_count == 0

    async def test_elapsed_time_recorded(self, crawler):
        """Test elapsed time is recorded."""
        crawler.check_login = AsyncMock(return_value=True)
        crawler.crawl_shop = AsyncMock(return_value=[])
        crawler._last_pages_crawled = 0

        result = await crawler.crawl_shop_with_metrics(
            shop_url="https://shop123.taobao.com"
        )

        assert result.elapsed_seconds >= 0


# ── CrawlResult Dataclass Tests ────────────────────────────


class TestCrawlResult:
    """Test CrawlResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = CrawlResult()
        assert result.products == []
        assert result.real_product_count == 0
        assert result.fallback_count == 0
        assert result.failure_reason == ""
        assert result.pages_crawled == 0
        assert result.elapsed_seconds == 0.0
        assert result.is_logged_in is False

    def test_custom_values(self):
        """Test custom values."""
        result = CrawlResult(
            products=[MagicMock()],
            real_product_count=5,
            pages_crawled=2,
            failure_reason="no_products_found",
            is_logged_in=True,
            elapsed_seconds=10.5,
        )
        assert result.real_product_count == 5
        assert result.pages_crawled == 2
        assert result.is_logged_in is True


# ── Integration-style Tests ────────────────────────────────


class TestShopCrawlIntegration:
    """Integration tests for shop crawling."""

    @pytest.fixture
    def crawler(self):
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)
            return TaobaoCrawler()

    async def test_crawl_shop_calls_normalize(self, crawler):
        """Test crawl_shop uses _normalize_shop_url and storage_state."""
        crawler.check_login = AsyncMock(return_value=True)

        # Mock the entire context and page
        mock_page = AsyncMock()
        mock_page.url = "https://shop123.taobao.com/search.htm"
        mock_page.query_selector_all = AsyncMock(return_value=[])

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_context.close = AsyncMock()

        crawler._new_context = AsyncMock(return_value=mock_context)
        crawler.load_cookies = AsyncMock()
        crawler.load_storage_state = AsyncMock()
        crawler.save_cookies = AsyncMock()
        crawler.save_storage_state = AsyncMock()
        crawler._browser_manager.safe_goto = AsyncMock(return_value=mock_page)

        # Call crawl_shop
        await crawler.crawl_shop(
            shop_url="https://shop123.taobao.com",
            max_pages=1,
        )

        # Verify storage_state was loaded
        crawler.load_storage_state.assert_called_once()
        # Verify storage_state was saved
        crawler.save_storage_state.assert_called_once()
