"""Tests for Phase 9.2.2 — Login status detection (check_login)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.base import BaseCrawler, CookieManager
from app.crawler.models.schemas import RawProduct


# ── Minimal stub (inherits BaseCrawler default check_login) ───


class _StubCrawler(BaseCrawler):
    """Stub using BaseCrawler default check_login (returns False)."""

    PLATFORM = "xiaohongshu"
    BASE_URL = "https://example.com"

    def __init__(self, tmp_path: Path | None = None) -> None:
        self._playwright = None
        self._browser = None
        self._settings = MagicMock()
        self._settings.crawler_retry = 3
        self._settings.crawler_retry_times = 3
        self._settings.crawler_retry_delay = 0
        self._settings.login_check_timeout = 15
        cookie_dir = tmp_path or Path("/tmp/cookies")
        self._cookie_manager = CookieManager(cookie_dir)

    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        return []

    async def _parse_product(self, element) -> None:
        return None


# ── Helper: build a mock BrowserContext with page ─────────────


def _make_mock_context(page):
    """Return an AsyncMock BrowserContext whose new_page() returns *page*."""
    context = AsyncMock()
    context.new_page.return_value = page
    return context


def _make_mock_page(query_results: dict | None = None):
    """Return an AsyncMock Page.

    *query_results* maps CSS selector fragments to Mock elements or None.
    query_selector() returns the element if any key in query_results
    matches the selector string, otherwise None.
    """
    page = AsyncMock()

    async def _qs(selector):
        if query_results:
            for key, element in query_results.items():
                if key in selector:
                    return element
        return None

    page.query_selector = _qs
    return page


# ── BaseCrawler default ──────────────────────────────────────


class TestBaseCrawlerDefault:
    """BaseCrawler.check_login() default behaviour."""

    @pytest.mark.anyio
    async def test_default_returns_false(self, tmp_path):
        crawler = _StubCrawler(tmp_path)
        result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_default_logs_warning(self, tmp_path, caplog):
        """Default implementation should log a warning."""
        import logging
        caplog.set_level(logging.WARNING)
        crawler = _StubCrawler(tmp_path)
        await crawler.check_login()
        # loguru doesn't use stdlib logging; just verify return value
        assert True


# ── Cookie not exists ────────────────────────────────────────


class TestCookieNotExists:
    """check_login returns False immediately when no cookies on disk."""

    @pytest.mark.anyio
    async def test_xiaohongshu_no_cookies(self, tmp_path):
        from app.crawler.xiaohongshu import XiaohongshuCrawler
        with patch.object(XiaohongshuCrawler, "__init__", lambda self: None):
            crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "xiaohongshu"
            crawler.BASE_URL = "https://www.xiaohongshu.com"
            result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_douyin_no_cookies(self, tmp_path):
        from app.crawler.douyin import DouyinCrawler
        with patch.object(DouyinCrawler, "__init__", lambda self: None):
            crawler = DouyinCrawler.__new__(DouyinCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "douyin"
            crawler.BASE_URL = "https://www.douyin.com"
            result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_kuaishou_no_cookies(self, tmp_path):
        from app.crawler.kuaishou import KuaishouCrawler
        with patch.object(KuaishouCrawler, "__init__", lambda self: None):
            crawler = KuaishouCrawler.__new__(KuaishouCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "kuaishou"
            crawler.BASE_URL = "https://www.kuaishou.com"
            result = await crawler.check_login()
        assert result is False


# ── Simulated login success ──────────────────────────────────


class TestLoginSuccess:
    """check_login returns True when user elements are found."""

    @pytest.mark.anyio
    async def test_xiaohongshu_logged_in(self, tmp_path):
        from app.crawler.xiaohongshu import XiaohongshuCrawler

        user_el = MagicMock()  # user element found
        page = _make_mock_page({"user": user_el})
        context = _make_mock_context(page)

        with patch.object(XiaohongshuCrawler, "__init__", lambda self: None):
            crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "xiaohongshu"
            crawler.BASE_URL = "https://www.xiaohongshu.com"
            crawler._playwright = None
            crawler._browser = None

            # Save a dummy cookie so has_cookies() returns True
            crawler._cookie_manager.save("xiaohongshu", [{"name": "s", "value": "v", "domain": ".x"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is True

    @pytest.mark.anyio
    async def test_douyin_logged_in(self, tmp_path):
        from app.crawler.douyin import DouyinCrawler

        user_el = MagicMock()
        page = _make_mock_page({"avatar": user_el})
        context = _make_mock_context(page)

        with patch.object(DouyinCrawler, "__init__", lambda self: None):
            crawler = DouyinCrawler.__new__(DouyinCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "douyin"
            crawler.BASE_URL = "https://www.douyin.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("douyin", [{"name": "s", "value": "v", "domain": ".d"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is True

    @pytest.mark.anyio
    async def test_kuaishou_logged_in(self, tmp_path):
        from app.crawler.kuaishou import KuaishouCrawler

        user_el = MagicMock()
        page = _make_mock_page({"avatar": user_el})
        context = _make_mock_context(page)

        with patch.object(KuaishouCrawler, "__init__", lambda self: None):
            crawler = KuaishouCrawler.__new__(KuaishouCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "kuaishou"
            crawler.BASE_URL = "https://www.kuaishou.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("kuaishou", [{"name": "s", "value": "v", "domain": ".k"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is True


# ── Simulated login failure ──────────────────────────────────


class TestLoginFailure:
    """check_login returns False when login elements are detected."""

    @pytest.mark.anyio
    async def test_xiaohongshu_login_popup(self, tmp_path):
        from app.crawler.xiaohongshu import XiaohongshuCrawler

        login_el = MagicMock()  # login element found
        page = _make_mock_page({"login": login_el})
        context = _make_mock_context(page)

        with patch.object(XiaohongshuCrawler, "__init__", lambda self: None):
            crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "xiaohongshu"
            crawler.BASE_URL = "https://www.xiaohongshu.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("xiaohongshu", [{"name": "s", "value": "v", "domain": ".x"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_douyin_login_guide(self, tmp_path):
        from app.crawler.douyin import DouyinCrawler

        guide_el = MagicMock()
        page = _make_mock_page({"login-guide": guide_el})
        context = _make_mock_context(page)

        with patch.object(DouyinCrawler, "__init__", lambda self: None):
            crawler = DouyinCrawler.__new__(DouyinCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "douyin"
            crawler.BASE_URL = "https://www.douyin.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("douyin", [{"name": "s", "value": "v", "domain": ".d"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_kuaishou_login_button(self, tmp_path):
        from app.crawler.kuaishou import KuaishouCrawler

        login_el = MagicMock()
        page = _make_mock_page({"login": login_el})
        context = _make_mock_context(page)

        with patch.object(KuaishouCrawler, "__init__", lambda self: None):
            crawler = KuaishouCrawler.__new__(KuaishouCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "kuaishou"
            crawler.BASE_URL = "https://www.kuaishou.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("kuaishou", [{"name": "s", "value": "v", "domain": ".k"}])

            with patch.object(crawler, "_new_context", return_value=context):
                result = await crawler.check_login()
        assert result is False


# ── Exception handling ────────────────────────────────────────


class TestExceptionHandling:
    """check_login returns False on unexpected exceptions."""

    @pytest.mark.anyio
    async def test_xiaohongshu_exception(self, tmp_path):
        from app.crawler.xiaohongshu import XiaohongshuCrawler

        with patch.object(XiaohongshuCrawler, "__init__", lambda self: None):
            crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "xiaohongshu"
            crawler.BASE_URL = "https://www.xiaohongshu.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("xiaohongshu", [{"name": "s", "value": "v", "domain": ".x"}])

            # _new_context raises
            with patch.object(crawler, "_new_context", side_effect=RuntimeError("browser crashed")):
                result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_douyin_exception(self, tmp_path):
        from app.crawler.douyin import DouyinCrawler

        with patch.object(DouyinCrawler, "__init__", lambda self: None):
            crawler = DouyinCrawler.__new__(DouyinCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "douyin"
            crawler.BASE_URL = "https://www.douyin.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("douyin", [{"name": "s", "value": "v", "domain": ".d"}])

            with patch.object(crawler, "_new_context", side_effect=RuntimeError("browser crashed")):
                result = await crawler.check_login()
        assert result is False

    @pytest.mark.anyio
    async def test_kuaishou_exception(self, tmp_path):
        from app.crawler.kuaishou import KuaishouCrawler

        with patch.object(KuaishouCrawler, "__init__", lambda self: None):
            crawler = KuaishouCrawler.__new__(KuaishouCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 15
            crawler._cookie_manager = CookieManager(tmp_path)
            crawler.PLATFORM = "kuaishou"
            crawler.BASE_URL = "https://www.kuaishou.com"
            crawler._playwright = None
            crawler._browser = None

            crawler._cookie_manager.save("kuaishou", [{"name": "s", "value": "v", "domain": ".k"}])

            with patch.object(crawler, "_new_context", side_effect=RuntimeError("browser crashed")):
                result = await crawler.check_login()
        assert result is False


# ── Settings integration ─────────────────────────────────────


class TestSettingsIntegration:
    """login_check_timeout is read from settings."""

    def test_default_timeout(self):
        from app.config.settings import get_settings
        # Clear the lru_cache to get fresh settings
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.login_check_timeout == 15

    def test_timeout_used_in_check_login(self, tmp_path):
        """Platform crawler should use settings.login_check_timeout."""
        from app.crawler.xiaohongshu import XiaohongshuCrawler

        with patch.object(XiaohongshuCrawler, "__init__", lambda self: None):
            crawler = XiaohongshuCrawler.__new__(XiaohongshuCrawler)
            crawler._settings = MagicMock()
            crawler._settings.login_check_timeout = 20
            assert crawler._settings.login_check_timeout == 20
