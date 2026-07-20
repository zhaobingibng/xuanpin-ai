"""Tests for Phase 9.7.5 — BrowserManager retry and UserAgentManager.

Covers: UserAgentManager, safe_goto, page recovery, random_delay/scroll/mouse_move.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawler.browser import (
    BrowserManager,
    UserAgentManager,
    random_delay,
    random_scroll,
    mouse_move,
)


# ── TestUserAgentManager ───────────────────────────────────────


class TestUserAgentManager:
    """Random User-Agent selection."""

    def test_get_random_returns_string(self):
        ua = UserAgentManager.get_random()
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_get_random_chrome(self):
        ua = UserAgentManager.get_random("chrome")
        assert "Chrome" in ua

    def test_get_random_edge(self):
        ua = UserAgentManager.get_random("edge")
        assert "Edg" in ua

    def test_get_random_mobile(self):
        ua = UserAgentManager.get_random("mobile")
        assert "Mobile" in ua or "iPhone" in ua or "Android" in ua

    def test_get_random_invalid_type_falls_back(self):
        ua = UserAgentManager.get_random("invalid_type")
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_chrome_agents_list(self):
        assert len(UserAgentManager.CHROME_AGENTS) >= 2

    def test_edge_agents_list(self):
        assert len(UserAgentManager.EDGE_AGENTS) >= 1

    def test_mobile_agents_list(self):
        assert len(UserAgentManager.MOBILE_AGENTS) >= 2

    def test_randomness(self):
        """Over 20 calls, at least 2 distinct UAs should appear."""
        uas = {UserAgentManager.get_random() for _ in range(20)}
        assert len(uas) >= 2


# ── TestBehaviorSimulation ─────────────────────────────────────


class TestBehaviorSimulation:
    """random_delay, random_scroll, mouse_move."""

    @pytest.mark.anyio
    async def test_random_delay_does_not_raise(self):
        await random_delay(1, 5)

    @pytest.mark.anyio
    async def test_random_scroll_calls_evaluate(self):
        page = AsyncMock()
        page.evaluate = AsyncMock()
        await random_scroll(page, times=2)
        assert page.evaluate.call_count == 2

    @pytest.mark.anyio
    async def test_random_scroll_distance_varies(self):
        page = AsyncMock()
        page.evaluate = AsyncMock()
        await random_scroll(page, times=3)
        # Each call passes a scrollBy JS string
        for call in page.evaluate.call_args_list:
            js = call[0][0]
            assert "scrollBy" in js

    @pytest.mark.anyio
    async def test_mouse_move_calls_page_mouse(self):
        page = AsyncMock()
        page.mouse = AsyncMock()
        page.mouse.move = AsyncMock()
        await mouse_move(page)
        page.mouse.move.assert_called_once()


# ── TestBrowserManagerSafeGoto ─────────────────────────────────


class TestBrowserManagerSafeGoto:
    """safe_goto with page crash recovery."""

    def _make_manager(self):
        settings = MagicMock()
        settings.browser_headless = True
        settings.browser_timeout = 30000
        settings.browser_user_agent = "test-ua"
        settings.browser_persistent = False
        settings.browser_user_data_dir = "./storage/browser_profile"
        cookie_manager = MagicMock()
        cookie_manager.load = MagicMock(return_value=[])
        return BrowserManager(settings, cookie_manager)

    @pytest.mark.anyio
    async def test_safe_goto_success(self):
        bm = self._make_manager()
        page = AsyncMock()
        page.goto = AsyncMock()

        result = await bm.safe_goto(page, "https://example.com", platform="test")
        assert result is page
        page.goto.assert_called_once()

    @pytest.mark.anyio
    async def test_safe_goto_recovers_on_error(self):
        bm = self._make_manager()
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("page crashed"))

        # Mock recovery
        new_page = AsyncMock()
        new_page.goto = AsyncMock()
        with patch.object(bm, "_recover_page", return_value=new_page):
            result = await bm.safe_goto(page, "https://example.com", platform="test")

        assert result is new_page

    @pytest.mark.anyio
    async def test_safe_goto_custom_timeout(self):
        bm = self._make_manager()
        page = AsyncMock()
        page.goto = AsyncMock()

        await bm.safe_goto(page, "https://example.com", timeout=5000, platform="test")
        call_kwargs = page.goto.call_args[1]
        assert call_kwargs["timeout"] == 5000

    @pytest.mark.anyio
    async def test_safe_goto_custom_wait_until(self):
        bm = self._make_manager()
        page = AsyncMock()
        page.goto = AsyncMock()

        await bm.safe_goto(
            page, "https://example.com",
            wait_until="domcontentloaded", platform="test",
        )
        call_kwargs = page.goto.call_args[1]
        assert call_kwargs["wait_until"] == "domcontentloaded"

    @pytest.mark.anyio
    async def test_recover_page_creates_new_context(self):
        bm = self._make_manager()
        bm._browser = MagicMock()

        new_ctx = AsyncMock()
        new_page = AsyncMock()
        new_page.goto = AsyncMock()
        new_ctx.new_page = AsyncMock(return_value=new_page)

        with patch.object(bm, "new_context", return_value=new_ctx):
            result = await bm._recover_page("test", "https://example.com", 30000, "networkidle")

        assert result is new_page

    @pytest.mark.anyio
    async def test_recover_page_raises_on_failure(self):
        bm = self._make_manager()
        bm._browser = MagicMock()

        with patch.object(bm, "new_context", side_effect=RuntimeError("browser dead")):
            with pytest.raises(RuntimeError, match="browser dead"):
                await bm._recover_page("test", "https://example.com", 30000, "networkidle")


# ── TestBrowserManagerContext ──────────────────────────────────


class TestBrowserManagerContext:
    """Context creation uses random User-Agent."""

    @pytest.mark.anyio
    async def test_new_context_uses_random_ua(self):
        settings = MagicMock()
        settings.browser_headless = True
        settings.browser_timeout = 30000
        settings.browser_user_agent = "static-ua"
        settings.browser_persistent = False
        settings.browser_user_data_dir = "./storage/browser_profile"
        cookie_manager = MagicMock()
        cookie_manager.load = MagicMock(return_value=[])

        bm = BrowserManager(settings, cookie_manager)
        bm._browser = MagicMock()

        mock_context = AsyncMock()
        bm._browser.new_context = AsyncMock(return_value=mock_context)

        ctx = await bm.new_context("test")
        assert ctx is mock_context

        # UA should come from UserAgentManager, not settings
        call_kwargs = bm._browser.new_context.call_args[1]
        assert call_kwargs["user_agent"] != "static-ua"
        assert len(call_kwargs["user_agent"]) > 20
