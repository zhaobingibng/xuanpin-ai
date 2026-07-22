"""Tests for BrowserManager — Phase 9.2.3."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.base import CookieManager
from app.crawler.browser import BrowserManager


# ── Fixtures ──────────────────────────────────────────────────


def _make_settings(**overrides):
    """Return a mock AppSettings with sensible defaults."""
    s = MagicMock()
    s.browser_headless = overrides.get("browser_headless", True)
    s.browser_timeout = overrides.get("browser_timeout", 30000)
    s.browser_user_agent = overrides.get(
        "browser_user_agent",
        "Mozilla/5.0 (Test) TestBot/1.0",
    )
    s.browser_persistent = overrides.get("browser_persistent", False)
    s.browser_user_data_dir = overrides.get(
        "browser_user_data_dir", "./storage/browser_profile"
    )
    return s


def _make_cookie_manager(tmp_path: Path) -> CookieManager:
    """Return a real CookieManager backed by tmp_path."""
    return CookieManager(tmp_path)


# ── start() ──────────────────────────────────────────────────


class TestStart:
    """BrowserManager.start() launches Playwright + Chromium."""

    @pytest.mark.anyio
    async def test_start_launches_browser(self, tmp_path):
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch("app.crawler.browser.async_playwright", return_value=mock_playwright):
            mock_playwright.start = AsyncMock(return_value=mock_playwright)
            await bm.start()

        assert bm._playwright is not None
        assert bm._browser is not None
        mock_playwright.chromium.launch.assert_called_once_with(headless=True)

    @pytest.mark.anyio
    async def test_start_idempotent(self, tmp_path):
        """Calling start() twice should not launch a second browser."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch("app.crawler.browser.async_playwright", return_value=mock_playwright):
            mock_playwright.start = AsyncMock(return_value=mock_playwright)
            await bm.start()
            await bm.start()  # second call

        # launch should only be called once
        assert mock_playwright.chromium.launch.call_count == 1

    @pytest.mark.anyio
    async def test_start_uses_headless_setting(self, tmp_path):
        settings = _make_settings(browser_headless=False)
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch("app.crawler.browser.async_playwright", return_value=mock_playwright):
            mock_playwright.start = AsyncMock(return_value=mock_playwright)
            await bm.start()

        mock_playwright.chromium.launch.assert_called_once_with(headless=False)


# ── new_context() ────────────────────────────────────────────


class TestNewContext:
    """BrowserManager.new_context() creates context with proper config."""

    @pytest.mark.anyio
    async def test_creates_context_with_config(self, tmp_path):
        settings = _make_settings(browser_user_agent="TestUA/2.0")
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        bm._browser = mock_browser  # skip start()

        ctx = await bm.new_context("xiaohongshu")

        assert ctx is mock_context
        # UA now comes from UserAgentManager.get_random(), not settings
        call_kwargs = mock_browser.new_context.call_args[1]
        assert isinstance(call_kwargs["user_agent"], str)
        assert len(call_kwargs["user_agent"]) > 10
        assert call_kwargs["viewport"] == {"width": 375, "height": 812}
        assert call_kwargs["locale"] == "zh-CN"

    @pytest.mark.anyio
    async def test_context_tracked(self, tmp_path):
        """Created contexts are tracked for cleanup."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = AsyncMock()
        bm._browser = mock_browser

        await bm.new_context("douyin")
        await bm.new_context("kuaishou")
        assert len(bm._contexts) == 2

    @pytest.mark.anyio
    async def test_loads_cookies(self, tmp_path):
        """new_context loads cookies via CookieManager."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        cm.save("xiaohongshu", [{"name": "sid", "value": "abc", "domain": ".xhs"}])

        bm = BrowserManager(settings, cm)
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        bm._browser = mock_browser

        await bm.new_context("xiaohongshu")

        mock_context.add_cookies.assert_called_once()

    @pytest.mark.anyio
    async def test_no_cookies_skips_add(self, tmp_path):
        """When no cookie file exists, add_cookies is not called."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        bm._browser = mock_browser

        await bm.new_context("xiaohongshu")

        mock_context.add_cookies.assert_not_called()

    @pytest.mark.anyio
    async def test_auto_starts_browser(self, tmp_path):
        """new_context auto-starts browser if not yet started."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        with patch("app.crawler.browser.async_playwright", return_value=mock_playwright):
            mock_playwright.start = AsyncMock(return_value=mock_playwright)
            ctx = await bm.new_context("xiaohongshu")

        assert ctx is mock_context
        assert bm._browser is mock_browser


# ── new_page() ───────────────────────────────────────────────


class TestNewPage:
    """BrowserManager.new_page() returns a Page."""

    @pytest.mark.anyio
    async def test_returns_page(self, tmp_path):
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        bm._browser = mock_browser

        page = await bm.new_page("kuaishou")

        assert page is mock_page
        mock_context.new_page.assert_called_once()


# ── close() ──────────────────────────────────────────────────


class TestClose:
    """BrowserManager.close() tears down all resources."""

    @pytest.mark.anyio
    async def test_close_all(self, tmp_path):
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()

        bm._playwright = mock_playwright
        bm._browser = mock_browser
        bm._contexts = [mock_context]

        await bm.close()

        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        assert bm._browser is None
        assert bm._playwright is None
        assert len(bm._contexts) == 0

    @pytest.mark.anyio
    async def test_close_idempotent(self, tmp_path):
        """close() on already-closed manager should not raise."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        # Nothing started
        await bm.close()  # should not raise

    @pytest.mark.anyio
    async def test_close_handles_context_error(self, tmp_path):
        """If context.close() raises, close() continues cleanup."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_context.close.side_effect = RuntimeError("context already closed")

        bm._playwright = mock_playwright
        bm._browser = mock_browser
        bm._contexts = [mock_context]

        await bm.close()  # should not raise

        # Browser and playwright still cleaned up
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_handles_browser_error(self, tmp_path):
        """If browser.close() raises, close() continues to stop playwright."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.close.side_effect = RuntimeError("browser crash")

        bm._playwright = mock_playwright
        bm._browser = mock_browser

        await bm.close()

        mock_playwright.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_multiple_contexts(self, tmp_path):
        """All tracked contexts are closed."""
        settings = _make_settings()
        cm = _make_cookie_manager(tmp_path)
        bm = BrowserManager(settings, cm)

        ctx1 = AsyncMock()
        ctx2 = AsyncMock()
        ctx3 = AsyncMock()
        bm._contexts = [ctx1, ctx2, ctx3]
        bm._browser = AsyncMock()
        bm._playwright = AsyncMock()

        await bm.close()

        ctx1.close.assert_called_once()
        ctx2.close.assert_called_once()
        ctx3.close.assert_called_once()


# ── Settings integration ─────────────────────────────────────


class TestBrowserSettings:
    """BrowserManager reads config from settings."""

    def test_browser_headless_default(self):
        from app.config.settings import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.browser_headless is False  # Phase 42.6: 可见浏览器模式

    def test_browser_timeout_default(self):
        from app.config.settings import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.browser_timeout == 30000

    def test_browser_user_agent_default(self):
        from app.config.settings import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert "Mozilla" in s.browser_user_agent


# ── BaseCrawler integration ──────────────────────────────────


class TestBaseCrawlerIntegration:
    """BaseCrawler delegates browser ops to BrowserManager."""

    def test_base_crawler_has_browser_manager(self):
        """BaseCrawler.__init__ creates a _browser_manager attribute."""
        from app.crawler.base import BaseCrawler
        # Verify the class has _new_context method (delegates to BrowserManager)
        assert hasattr(BaseCrawler, "_new_context")
        assert hasattr(BaseCrawler, "close")

    def test_base_crawler_no_playwright_attr(self):
        """BaseCrawler no longer has _playwright / _browser as direct attributes."""
        import inspect
        from app.crawler.base import BaseCrawler
        source = inspect.getsource(BaseCrawler.__init__)
        assert "self._playwright" not in source
        assert "self._browser " not in source  # space ensures not _browser_manager
        assert "_browser_manager" in source
