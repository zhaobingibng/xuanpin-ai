"""Tests for Phase 9.7.5 — Cookie session detection.

Covers: check_cookie() returning COOKIE_VALID / COOKIE_EXPIRED / COOKIE_MISSING.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.crawler.session import check_cookie, COOKIE_VALID, COOKIE_EXPIRED, COOKIE_MISSING


# ── Helpers ────────────────────────────────────────────────────


def _make_crawler(
    has_cookies: bool = True,
    login_ok: bool = True,
    check_raises: bool = False,
) -> MagicMock:
    """Build a mock crawler with controllable behavior."""
    crawler = MagicMock()
    crawler.PLATFORM = "xiaohongshu"
    crawler.has_cookies = MagicMock(return_value=has_cookies)
    crawler.check_login = AsyncMock(
        return_value=login_ok,
        side_effect=RuntimeError("check failed") if check_raises else None,
    )
    crawler.close = AsyncMock()
    return crawler


# ── TestCheckCookie ────────────────────────────────────────────


class TestCheckCookie:
    """check_cookie() returns correct status."""

    @pytest.mark.anyio
    async def test_cookie_valid(self):
        crawler = _make_crawler(has_cookies=True, login_ok=True)
        status = await check_cookie(crawler)
        assert status == COOKIE_VALID

    @pytest.mark.anyio
    async def test_cookie_expired(self):
        crawler = _make_crawler(has_cookies=True, login_ok=False)
        status = await check_cookie(crawler)
        assert status == COOKIE_EXPIRED

    @pytest.mark.anyio
    async def test_cookie_missing(self):
        crawler = _make_crawler(has_cookies=False)
        status = await check_cookie(crawler)
        assert status == COOKIE_MISSING

    @pytest.mark.anyio
    async def test_cookie_check_exception_returns_expired(self):
        """If check_login raises, treat as EXPIRED."""
        crawler = _make_crawler(has_cookies=True, check_raises=True)
        status = await check_cookie(crawler)
        assert status == COOKIE_EXPIRED

    @pytest.mark.anyio
    async def test_missing_skips_check_login(self):
        """When cookie file is missing, check_login should not be called."""
        crawler = _make_crawler(has_cookies=False)
        await check_cookie(crawler)
        crawler.check_login.assert_not_called()

    @pytest.mark.anyio
    async def test_valid_calls_close(self):
        crawler = _make_crawler(has_cookies=True, login_ok=True)
        await check_cookie(crawler)
        crawler.close.assert_called_once()

    @pytest.mark.anyio
    async def test_expired_calls_close(self):
        crawler = _make_crawler(has_cookies=True, login_ok=False)
        await check_cookie(crawler)
        crawler.close.assert_called_once()

    @pytest.mark.anyio
    async def test_missing_does_not_call_close(self):
        """No need to close if we never opened a browser."""
        crawler = _make_crawler(has_cookies=False)
        await check_cookie(crawler)
        crawler.close.assert_not_called()

    @pytest.mark.anyio
    async def test_exception_calls_close(self):
        """Even on exception, close should be called."""
        crawler = _make_crawler(has_cookies=True, check_raises=True)
        await check_cookie(crawler)
        crawler.close.assert_called_once()


# ── TestConstants ──────────────────────────────────────────────


class TestConstants:
    """Status constants are correct strings."""

    def test_valid(self):
        assert COOKIE_VALID == "COOKIE_VALID"

    def test_expired(self):
        assert COOKIE_EXPIRED == "COOKIE_EXPIRED"

    def test_missing(self):
        assert COOKIE_MISSING == "COOKIE_MISSING"
