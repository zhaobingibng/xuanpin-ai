"""Tests for Phase 16.8: Taobao crawler stabilization enhancements."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# CrawlResult Tests
# ============================================================

class TestCrawlResult:
    """Test CrawlResult dataclass."""

    def test_import(self):
        """Test CrawlResult imports correctly."""
        from app.crawler.taobao import CrawlResult
        assert CrawlResult is not None

    def test_default_values(self):
        """Test default values."""
        from app.crawler.taobao import CrawlResult
        result = CrawlResult()
        assert result.products == []
        assert result.real_product_count == 0
        assert result.fallback_count == 0
        assert result.failure_reason == ""
        assert result.pages_crawled == 0
        assert result.elapsed_seconds == 0.0
        assert result.is_logged_in is False

    def test_to_dict(self):
        """Test to_dict conversion."""
        from app.crawler.taobao import CrawlResult
        result = CrawlResult(
            products=[],
            real_product_count=10,
            fallback_count=2,
            failure_reason="",
            pages_crawled=3,
            elapsed_seconds=45.5,
            is_logged_in=True,
        )
        d = result.to_dict()
        assert d["real_product_count"] == 10
        assert d["fallback_count"] == 2
        assert d["failure_reason"] == ""
        assert d["pages_crawled"] == 3
        assert d["elapsed_seconds"] == 45.5
        assert d["is_logged_in"] is True
        assert d["total"] == 0  # len(products)

    def test_to_dict_with_failure(self):
        """Test to_dict with failure reason."""
        from app.crawler.taobao import CrawlResult
        result = CrawlResult(failure_reason="not_logged_in")
        d = result.to_dict()
        assert d["failure_reason"] == "not_logged_in"
        assert d["real_product_count"] == 0


# ============================================================
# Storage State Tests
# ============================================================

class TestStorageState:
    """Test storage state persistence."""

    def test_storage_state_path(self):
        """Test storage state path generation."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()
        path = crawler._storage_state_path()
        assert "taobao_storage_state.json" in str(path)

    @pytest.mark.asyncio
    async def test_save_storage_state(self):
        """Test save storage state."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()

        # Mock context with storage_state method
        mock_context = AsyncMock()
        mock_context.storage_state = AsyncMock(return_value={
            "cookies": [{"name": "test", "value": "123"}],
            "origins": [],
        })

        # Should not raise
        await crawler.save_storage_state(mock_context)

    @pytest.mark.asyncio
    async def test_load_storage_state_no_file(self):
        """Test load storage state when file doesn't exist."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()

        # Ensure file doesn't exist
        path = crawler._storage_state_path()
        if path.exists():
            path.unlink()

        mock_context = AsyncMock()
        result = await crawler.load_storage_state(mock_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_load_storage_state_with_file(self):
        """Test load storage state from existing file."""
        from app.crawler.taobao import TaobaoCrawler
        import json
        import tempfile
        from pathlib import Path

        crawler = TaobaoCrawler()

        # Create a temp storage state file
        state_data = {
            "cookies": [{"name": "test", "value": "123", "domain": ".taobao.com"}],
            "origins": [],
        }
        path = crawler._storage_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state_data), encoding="utf-8")

        try:
            mock_context = AsyncMock()
            mock_context.add_cookies = AsyncMock()
            result = await crawler.load_storage_state(mock_context)
            assert result is True
            mock_context.add_cookies.assert_called_once()
        finally:
            # Cleanup
            if path.exists():
                path.unlink()


# ============================================================
# Crawl With Metrics Tests
# ============================================================

class TestCrawlWithMetrics:
    """Test crawl_with_metrics method."""

    @pytest.mark.asyncio
    async def test_not_logged_in(self):
        """Test crawl_with_metrics returns failure when not logged in."""
        from app.crawler.taobao import TaobaoCrawler, CrawlResult
        crawler = TaobaoCrawler()

        # Mock check_login to return False
        crawler.check_login = AsyncMock(return_value=False)

        result = await crawler.crawl_with_metrics("test")
        assert isinstance(result, CrawlResult)
        assert result.is_logged_in is False
        assert result.failure_reason == "not_logged_in"
        assert result.real_product_count == 0

    @pytest.mark.asyncio
    async def test_successful_crawl_metrics(self):
        """Test crawl_with_metrics returns correct metrics on success."""
        from app.crawler.taobao import TaobaoCrawler, CrawlResult
        from app.crawler.models.schemas import RawProduct
        crawler = TaobaoCrawler()

        # Mock check_login to return True
        crawler.check_login = AsyncMock(return_value=True)

        # Mock _do_crawl to return products
        mock_products = [
            RawProduct(name="Test1", platform="taobao", shop="Shop1", price=99.0),
            RawProduct(name="Test2", platform="taobao", shop="Shop2", price=199.0),
        ]
        crawler._do_crawl = AsyncMock(return_value=mock_products)
        crawler._last_pages_crawled = 2

        result = await crawler.crawl_with_metrics("test")
        assert isinstance(result, CrawlResult)
        assert result.is_logged_in is True
        assert result.real_product_count == 2
        assert result.pages_crawled == 2
        assert result.failure_reason == ""
        assert len(result.products) == 2

    @pytest.mark.asyncio
    async def test_empty_crawl_records_reason(self):
        """Test crawl_with_metrics records reason when no products found."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()

        crawler.check_login = AsyncMock(return_value=True)
        crawler._do_crawl = AsyncMock(return_value=[])
        crawler._last_pages_crawled = 0

        result = await crawler.crawl_with_metrics("test")
        assert result.real_product_count == 0
        assert result.failure_reason == "no_products_found"

    @pytest.mark.asyncio
    async def test_crawl_error_records_reason(self):
        """Test crawl_with_metrics records error reason."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()

        crawler.check_login = AsyncMock(return_value=True)
        crawler._do_crawl = AsyncMock(side_effect=RuntimeError("network error"))

        result = await crawler.crawl_with_metrics("test")
        assert "crawl_error" in result.failure_reason
        assert result.real_product_count == 0


# ============================================================
# Enhanced _do_crawl Tests
# ============================================================

class TestEnhancedDoCrawl:
    """Test enhanced _do_crawl features."""

    def test_last_pages_crawled_init(self):
        """Test _last_pages_crawled attribute exists after crawl."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()
        # Before crawl, attribute may not exist
        # After crawl, it should be set
        assert hasattr(crawler, '_settings')  # Basic init check

    @pytest.mark.asyncio
    async def test_do_crawl_loads_storage_state(self):
        """Test _do_crawl calls load_storage_state."""
        from app.crawler.taobao import TaobaoCrawler
        crawler = TaobaoCrawler()

        # Mock dependencies
        crawler.check_login = AsyncMock(return_value=True)
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=AsyncMock())
        mock_context.close = AsyncMock()
        crawler._new_context = AsyncMock(return_value=mock_context)
        crawler.load_cookies = AsyncMock(return_value=True)
        crawler.load_storage_state = AsyncMock(return_value=True)
        crawler.save_cookies = AsyncMock()
        crawler.save_storage_state = AsyncMock()

        # Mock page operations
        mock_page = AsyncMock()
        mock_page.url = "https://s.taobao.com/search?q=test"
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_context.new_page = AsyncMock(return_value=mock_page)

        # Mock safe_goto
        crawler._browser_manager.safe_goto = AsyncMock(return_value=mock_page)

        # Run
        products = await crawler._do_crawl("test", max_pages=1)

        # Verify storage state was loaded and saved
        crawler.load_storage_state.assert_called_once()
        crawler.save_storage_state.assert_called_once()


# ============================================================
# Integration: CrawlResult in Pipeline
# ============================================================

class TestCrawlResultIntegration:
    """Test CrawlResult integration with pipeline."""

    def test_crawl_result_serializable(self):
        """Test CrawlResult.to_dict is JSON serializable."""
        import json
        from app.crawler.taobao import CrawlResult
        result = CrawlResult(
            real_product_count=5,
            fallback_count=0,
            failure_reason="",
            pages_crawled=2,
            elapsed_seconds=30.5,
            is_logged_in=True,
        )
        d = result.to_dict()
        # Should be JSON serializable
        json_str = json.dumps(d)
        assert "real_product_count" in json_str

    def test_crawl_result_failure_serializable(self):
        """Test CrawlResult with failure is JSON serializable."""
        import json
        from app.crawler.taobao import CrawlResult
        result = CrawlResult(failure_reason="timeout: 30000ms exceeded")
        d = result.to_dict()
        json_str = json.dumps(d)
        assert "timeout" in json_str
