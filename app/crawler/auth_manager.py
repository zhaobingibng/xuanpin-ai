"""AuthManager — centralized login state management for crawlers.

Provides:
- Login state detection via browser storage_state
- Session persistence to database
- Pre-crawl validation (ACTIVE / EXPIRED / UNKNOWN)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger


class LoginStatus(str, Enum):
    """Login status enumeration (mirrors model)."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


@dataclass
class AuthState:
    """Immutable login state result."""

    status: LoginStatus
    platform: str
    username: str | None = None
    checked_at: datetime | None = None
    detail: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == LoginStatus.ACTIVE

    @property
    def is_expired(self) -> bool:
        return self.status == LoginStatus.EXPIRED

    @property
    def is_unknown(self) -> bool:
        return self.status == LoginStatus.UNKNOWN


class AuthManager:
    """Centralized login state manager.

    Usage:
        auth = AuthManager(cookie_dir="./storage/cookies")
        state = await auth.check_login("taobao")
        if state.is_active:
            # proceed with crawl
        elif state.is_expired:
            # prompt re-login
    """

    # New state file paths (Phase 22)
    STATE_FILE_PATHS = {
        "taobao": Path("storage/taobao_state.json"),
        "1688": Path("storage/alibaba_state.json"),
        "alibaba": Path("storage/alibaba_state.json"),
    }

    def __init__(self, cookie_dir: str | Path) -> None:
        self._cookie_dir = Path(cookie_dir)
        self._cookie_dir.mkdir(parents=True, exist_ok=True)

    def _storage_state_path(self, platform: str) -> Path:
        """Get storage_state file path for a platform.
        
        First checks new state file paths, then falls back to cookie_dir.
        """
        # Check new state file paths first
        if platform in self.STATE_FILE_PATHS:
            new_path = self.STATE_FILE_PATHS[platform]
            if new_path.exists() and new_path.stat().st_size > 0:
                return new_path
        
        # Fall back to cookie_dir
        return self._cookie_dir / f"{platform}_storage_state.json"

    def _cookies_path(self, platform: str) -> Path:
        """Get cookies file path for a platform."""
        return self._cookie_dir / f"{platform}.json"

    def has_storage_state(self, platform: str) -> bool:
        """Check if storage_state file exists."""
        path = self._storage_state_path(platform)
        return path.exists() and path.stat().st_size > 0

    def has_cookies(self, platform: str) -> bool:
        """Check if cookies file exists."""
        path = self._cookies_path(platform)
        return path.exists() and path.stat().st_size > 0

    def load_storage_state_data(self, platform: str) -> dict[str, Any] | None:
        """Load storage_state data from file.

        Returns:
            Dict with cookies/localStorage/sessionStorage, or None if not found.
        """
        path = self._storage_state_path(platform)
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
        except Exception as e:
            logger.warning("[AuthManager] Failed to load storage_state for {}: {}", platform, e)
            return None

    def extract_username_from_storage(self, platform: str) -> str | None:
        """Try to extract username from storage_state cookies.

        Looks for common Taobao cookie fields that contain username.
        """
        data = self.load_storage_state_data(platform)
        if not data:
            return None

        cookies = data.get("cookies", [])
        for cookie in cookies:
            name = cookie.get("name", "")
            # Taobao stores username in these cookies
            if name in ("_nk_", "snk", "nick", "login_current_pk"):
                value = cookie.get("value", "")
                if value and value not in ("登录", "亲，请登录"):
                    # URL decode if needed
                    try:
                        from urllib.parse import unquote
                        decoded = unquote(value)
                        if decoded and decoded not in ("登录", "亲，请登录"):
                            return decoded
                    except Exception:
                        return value
        return None

    async def check_login_state(
        self,
        platform: str,
        browser_manager: Any = None,
    ) -> AuthState:
        """Check login state for a platform.

        Args:
            platform: Platform name (taobao, 1688, etc.)
            browser_manager: Optional BrowserManager for live detection.

        Returns:
            AuthState with status, username, and detail.
        """
        now = datetime.now()

        # Step 1: Check if storage_state exists
        if not self.has_storage_state(platform) and not self.has_cookies(platform):
            logger.info("[AuthManager] No cookies/storage_state for platform: {}", platform)
            return AuthState(
                status=LoginStatus.UNKNOWN,
                platform=platform,
                checked_at=now,
                detail="no_cookies_or_storage_state",
            )

        # Step 2: Try to extract username from storage
        username = self.extract_username_from_storage(platform)

        # Step 3: If browser_manager provided, do live detection
        if browser_manager is not None:
            try:
                is_logged_in, detected_username = await self._live_check(
                    platform, browser_manager
                )
                if detected_username:
                    username = detected_username

                if is_logged_in:
                    logger.info("[AuthManager] {} login ACTIVE (user: {})", platform, username)
                    return AuthState(
                        status=LoginStatus.ACTIVE,
                        platform=platform,
                        username=username,
                        checked_at=now,
                        detail="live_check_passed",
                    )
                else:
                    logger.warning("[AuthManager] {} login EXPIRED", platform)
                    return AuthState(
                        status=LoginStatus.EXPIRED,
                        platform=platform,
                        username=username,
                        checked_at=now,
                        detail="live_check_failed",
                    )
            except Exception as e:
                logger.warning("[AuthManager] Live check failed for {}: {}", platform, e)
                # Fall through to cookie-based check

        # Step 4: Cookie-based heuristic
        if self.has_storage_state(platform) or self.has_cookies(platform):
            logger.info(
                "[AuthManager] {} login UNKNOWN (cookies exist, no live check)",
                platform,
            )
            return AuthState(
                status=LoginStatus.UNKNOWN,
                platform=platform,
                username=username,
                checked_at=now,
                detail="cookies_exist_no_live_check",
            )

        return AuthState(
            status=LoginStatus.UNKNOWN,
            platform=platform,
            checked_at=now,
            detail="no_evidence",
        )

    async def _live_check(
        self,
        platform: str,
        browser_manager: Any,
    ) -> tuple[bool, str | None]:
        """Perform live browser login check.

        Returns:
            (is_logged_in, username)
        """
        context = None
        try:
            context = await browser_manager.new_context(platform)
            page = await context.new_page()

            # Navigate based on platform
            if platform == "taobao":
                url = "https://www.taobao.com"
                login_selectors = [
                    "[class*='nick']",
                    ".site-nav-user .site-nav-user-hd",
                    ".member-nick",
                ]
            elif platform == "1688":
                url = "https://www.1688.com"
                login_selectors = [
                    "[class*='nick']",
                    ".member-nick",
                ]
            else:
                return False, None

            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            for sel in login_selectors:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and text not in ("登录", "亲，请登录"):
                        return True, text[:50]

            return False, None

        finally:
            if context:
                await context.close()

    def can_crawl(self, platform: str) -> tuple[bool, str]:
        """Quick check if crawl should proceed based on cached state.

        This is a fast, non-browser check using stored cookies.

        Returns:
            (should_proceed, reason)
        """
        if self.has_storage_state(platform) or self.has_cookies(platform):
            return True, "cookies_exist"
        return False, "no_login_credentials"
