"""Tests for Phase 9.2 crawler enhancements: retry, cookie, login detection, parse_count."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.base import BaseCrawler, CookieManager
from app.crawler.models.schemas import RawProduct


# ── Concrete stub for testing ─────────────────────────────────


class _StubCrawler(BaseCrawler):
    """Minimal concrete crawler for unit tests."""

    PLATFORM = "xiaohongshu"
    BASE_URL = "https://example.com"

    def __init__(self, tmp_path: Path | None = None) -> None:
        """Initialize with minimal dependencies."""
        self._playwright = None
        self._browser = None
        cookie_dir = tmp_path or Path(tempfile.mkdtemp())
        cookie_dir.mkdir(parents=True, exist_ok=True)
        self._cookie_manager = CookieManager(cookie_dir)
        # Mock settings
        self._settings = MagicMock()
        self._settings.crawler_retry = 3
        self._settings.crawler_retry_times = 3
        self._settings.crawler_retry_delay = 0
        self._settings.crawler_headless = True
        self._settings.crawler_user_agent = "TestBot/1.0"

    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        return [
            RawProduct(
                name=f"{keyword}-item",
                platform=self.PLATFORM,
                shop="test-shop",
                price=99.0,
            )
        ]

    async def _parse_product(self, element) -> RawProduct | None:
        return None


class _FailingCrawler(_StubCrawler):
    """Crawler that always raises."""

    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        raise RuntimeError("Simulated crawl failure")


# ── parse_count enhancement: 'w' / 'W' ────────────────────────


class TestParseCountEnhanced:
    """Test parse_count with w/W shorthand for 万."""

    def test_lowercase_w(self):
        assert BaseCrawler.parse_count("3.5w") == 35000

    def test_uppercase_W(self):
        assert BaseCrawler.parse_count("2.1W") == 21000

    def test_integer_w(self):
        assert BaseCrawler.parse_count("5w") == 50000

    def test_wan_still_works(self):
        assert BaseCrawler.parse_count("1.2万") == 12000

    def test_yi_still_works(self):
        assert BaseCrawler.parse_count("1.5亿") == 150_000_000

    def test_plain_number(self):
        assert BaseCrawler.parse_count("500") == 500

    def test_empty(self):
        assert BaseCrawler.parse_count("") == 0

    def test_text_with_w_context(self):
        assert BaseCrawler.parse_count("已售3.2w件") == 32000

    def test_text_with_W_context(self):
        assert BaseCrawler.parse_count("浏览1.8W次") == 18000


# ── Cookie persistence ────────────────────────────────────────


class TestCookiePersistence:
    """Test cookie save and load with mock BrowserContext."""

    @pytest.mark.anyio
    async def test_save_cookies(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_context = AsyncMock()
        mock_context.cookies.return_value = [
            {"name": "session", "value": "abc123", "domain": ".example.com"},
            {"name": "token", "value": "xyz789", "domain": ".example.com"},
        ]

        await crawler.save_cookies(mock_context)

        cookie_file = tmp_path / "xiaohongshu.json"
        assert cookie_file.exists()
        data = json.loads(cookie_file.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["name"] == "session"

    @pytest.mark.anyio
    async def test_load_cookies(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        cookie_file = tmp_path / "xiaohongshu.json"
        cookies = [
            {"name": "session", "value": "abc123", "domain": ".example.com"},
        ]
        cookie_file.write_text(json.dumps(cookies), encoding="utf-8")

        mock_context = AsyncMock()
        result = await crawler.load_cookies(mock_context)

        assert result is True
        mock_context.add_cookies.assert_called_once_with(cookies)

    @pytest.mark.anyio
    async def test_load_cookies_no_file(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_context = AsyncMock()

        result = await crawler.load_cookies(mock_context)

        assert result is False
        mock_context.add_cookies.assert_not_called()

    @pytest.mark.anyio
    async def test_load_cookies_empty_file(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        cookie_file = tmp_path / "xiaohongshu.json"
        cookie_file.write_text("[]", encoding="utf-8")

        mock_context = AsyncMock()
        result = await crawler.load_cookies(mock_context)

        assert result is False

    def test_has_cookies_true(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        (tmp_path / "xiaohongshu.json").write_text("[]", encoding="utf-8")
        assert crawler.has_cookies() is True

    def test_has_cookies_false(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        assert crawler.has_cookies() is False


# ── Retry mechanism ───────────────────────────────────────────


class TestRetryMechanism:
    """Test _with_retry retry logic."""

    @pytest.mark.anyio
    async def test_succeeds_first_try(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_func = AsyncMock(return_value="ok")

        result = await crawler._with_retry(mock_func, "arg1", kwarg1="val")

        assert result == "ok"
        assert mock_func.call_count == 1

    @pytest.mark.anyio
    async def test_succeeds_after_retry(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_func = AsyncMock(
            side_effect=[RuntimeError("fail1"), RuntimeError("fail2"), "ok"]
        )

        with patch("app.crawler.base.asyncio.sleep", new_callable=AsyncMock):
            result = await crawler._with_retry(mock_func)

        assert result == "ok"
        assert mock_func.call_count == 3

    @pytest.mark.anyio
    async def test_fails_after_all_retries(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_func = AsyncMock(side_effect=RuntimeError("always fails"))

        with patch("app.crawler.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="always fails"):
                await crawler._with_retry(mock_func)

        assert mock_func.call_count == 3  # settings.crawler_retry = 3

    @pytest.mark.anyio
    async def test_retry_waits_between_attempts(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        mock_func = AsyncMock(
            side_effect=[RuntimeError("fail"), "ok"]
        )

        with patch("app.crawler.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await crawler._with_retry(mock_func)
            mock_sleep.assert_called_once_with(0)  # crawler_retry_delay = 0


# ── Template method: crawl() → _do_crawl() ────────────────────


class TestTemplateMethod:
    """Test that crawl() wraps _do_crawl() with retry and logging."""

    @pytest.mark.anyio
    async def test_crawl_calls_do_crawl(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        products = await crawler.crawl(keyword="面膜", max_pages=2)
        assert len(products) == 1
        assert products[0].name == "面膜-item"

    @pytest.mark.anyio
    async def test_crawl_returns_empty_on_failure(self, tmp_path):
        crawler = _FailingCrawler(tmp_path)
        with patch("app.crawler.base.asyncio.sleep", new_callable=AsyncMock):
            products = await crawler.crawl(keyword="test")
        assert products == []

    @pytest.mark.anyio
    async def test_crawl_retries_on_failure(self, tmp_path):
        """Verify _do_crawl is retried via _with_retry."""
        call_count = 0

        class _FlakyCrawler(_StubCrawler):
            async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise RuntimeError("transient error")
                return [RawProduct(name="ok", platform="test", shop="s", price=1.0)]

        crawler = _FlakyCrawler(tmp_path)
        with patch("app.crawler.base.asyncio.sleep", new_callable=AsyncMock):
            products = await crawler.crawl(keyword="test")

        assert len(products) == 1
        assert call_count == 3


# ── check_login default ──────────────────────────────────────


class TestCheckLogin:
    """Test default check_login implementation (BaseCrawler)."""

    @pytest.mark.anyio
    async def test_default_returns_false(self, tmp_path):
        """BaseCrawler.check_login() always returns False by default."""
        crawler = _StubCrawler(tmp_path)
        result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_default_returns_false_no_cookies(self, tmp_path):
        """Even without cookies, default check_login returns False."""
        crawler = _StubCrawler(tmp_path)
        result = await crawler.check_login()
        assert result is False


# ── RawProduct category field ────────────────────────────────


class TestRawProductCategory:
    """Test the new category field on RawProduct."""

    def test_default_category(self):
        p = RawProduct(name="商品", platform="test", shop="店", price=10.0)
        assert p.category == ""

    def test_explicit_category(self):
        p = RawProduct(name="面霜", platform="test", shop="店", price=10.0, category="美妆")
        assert p.category == "美妆"

    def test_to_db_kwargs_category_empty(self):
        p = RawProduct(name="商品", platform="test", shop="店", price=10.0)
        kwargs = p.to_db_kwargs()
        assert kwargs["category"] is None  # empty string → None

    def test_to_db_kwargs_category_set(self):
        p = RawProduct(name="面霜", platform="test", shop="店", price=10.0, category="美妆")
        kwargs = p.to_db_kwargs()
        assert kwargs["category"] == "美妆"

    def test_to_db_kwargs_has_url(self):
        p = RawProduct(
            name="商品", platform="test", shop="店", price=10.0,
            url="https://example.com/p/1",
        )
        kwargs = p.to_db_kwargs()
        assert kwargs["url"] == "https://example.com/p/1"


# ── Platform crawler imports ─────────────────────────────────


class TestPlatformCrawlerStructure:
    """Verify platform crawlers implement the correct interface."""

    def test_xiaohongshu_has_do_crawl(self):
        from app.crawler.xiaohongshu import XiaohongshuCrawler
        assert hasattr(XiaohongshuCrawler, "_do_crawl")
        assert hasattr(XiaohongshuCrawler, "check_login")
        assert XiaohongshuCrawler.PLATFORM == "xiaohongshu"

    def test_douyin_has_do_crawl(self):
        from app.crawler.douyin import DouyinCrawler
        assert hasattr(DouyinCrawler, "_do_crawl")
        assert hasattr(DouyinCrawler, "check_login")
        assert DouyinCrawler.PLATFORM == "douyin"

    def test_kuaishou_has_do_crawl(self):
        from app.crawler.kuaishou import KuaishouCrawler
        assert hasattr(KuaishouCrawler, "_do_crawl")
        assert hasattr(KuaishouCrawler, "check_login")
        assert KuaishouCrawler.PLATFORM == "kuaishou"

    def test_crawl_is_template_method(self):
        """Base class crawl() should be a concrete method, not abstract."""
        assert not getattr(BaseCrawler.crawl, "__isabstractmethod__", False)

    def test_do_crawl_is_abstract(self):
        """_do_crawl should be abstract."""
        assert getattr(BaseCrawler._do_crawl, "__isabstractmethod__", False)
