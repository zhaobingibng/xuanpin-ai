"""Abstract base crawler with shared Playwright browser management and cookie persistence."""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger
from playwright.async_api import (
    BrowserContext,
    Page,
)

from app.config.settings import get_settings
from app.crawler.browser import BrowserManager
from app.crawler.models.schemas import RawProduct

T = TypeVar("T")

VALID_PLATFORMS = frozenset({"xiaohongshu", "douyin", "kuaishou", "taobao", "1688"})


# ── Cookie Manager ────────────────────────────────────────────


class CookieManager:
    """Cookie file persistence manager.

    Centralises all cookie I/O for supported platforms.
    Raises ``ValueError`` for unsupported platform names.
    """

    def __init__(self, cookie_dir: str | Path) -> None:
        self._cookie_dir = Path(cookie_dir)

    # ── Validation ────────────────────────────────────────────

    def _validate_platform(self, platform: str) -> None:
        if platform not in VALID_PLATFORMS:
            raise ValueError(
                f"Unsupported platform: {platform}. "
                f"Valid platforms: {sorted(VALID_PLATFORMS)}"
            )

    # ── Public API ────────────────────────────────────────────

    def get_cookie_path(self, platform: str) -> Path:
        """Return the cookie file path for *platform*."""
        self._validate_platform(platform)
        return self._cookie_dir / f"{platform}.json"

    def save(self, platform: str, cookies: list[dict]) -> None:
        """Persist *cookies* to disk for *platform*."""
        self._validate_platform(platform)
        self._cookie_dir.mkdir(parents=True, exist_ok=True)
        path = self._cookie_dir / f"{platform}.json"
        path.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[{}] Cookie 保存成功 -> {}", platform, path)

    def load(self, platform: str) -> list[dict]:
        """Load cookies from disk. Returns ``[]`` if file missing or corrupt."""
        self._validate_platform(platform)
        path = self._cookie_dir / f"{platform}.json"
        if not path.exists():
            logger.info("[{}] Cookie 文件不存在", platform)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("[{}] Cookie 加载成功 ({}条)", platform, len(data))
            return data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("[{}] Cookie 文件损坏, 已忽略: {}", platform, e)
            return []

    def exists(self, platform: str) -> bool:
        """Check whether the cookie file exists for *platform*."""
        self._validate_platform(platform)
        return self.get_cookie_path(platform).exists()

    def clear(self, platform: str) -> None:
        """Delete the cookie file for *platform*."""
        self._validate_platform(platform)
        path = self._cookie_dir / f"{platform}.json"
        if path.exists():
            path.unlink()
            logger.info("[{}] Cookie 已清除", platform)

    def clear_all(self) -> None:
        """Delete all cookie files in the directory."""
        if not self._cookie_dir.exists():
            return
        for path in self._cookie_dir.glob("*.json"):
            path.unlink()
            logger.info("Cookie 已清除: {}", path.name)


# ── BaseCrawler ───────────────────────────────────────────────


class BaseCrawler(ABC):
    """Base class for all platform crawlers.

    Provides shared browser lifecycle, cookie persistence,
    login detection, failure retry, and common parsing utilities.
    Subclasses implement ``_do_crawl`` and ``_parse_product``.
    """

    PLATFORM: str = ""
    BASE_URL: str = ""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cookie_manager = CookieManager(self._settings.cookie_dir)
        self._browser_manager = BrowserManager(self._settings, self._cookie_manager)

    # ── Browser lifecycle (delegates to BrowserManager) ───────

    async def _new_context(self) -> BrowserContext:
        """Create a new browser context via BrowserManager."""
        return await self._browser_manager.new_context(self.PLATFORM)

    async def close(self) -> None:
        """Close browser and stop Playwright via BrowserManager."""
        await self._browser_manager.close()

    # ── Cookie management (delegates to CookieManager) ────────

    async def save_cookies(self, context: BrowserContext) -> None:
        """Persist browser cookies to file via CookieManager."""
        cookies = await context.cookies()
        self._cookie_manager.save(self.PLATFORM, cookies)

    async def load_cookies(self, context: BrowserContext) -> bool:
        """Load cookies from file into the browser context. Return False if none.

        Persistent 模式：持久上下文已通过 user_data_dir 自动管理 Cookie，
        跳过手动 JSON 注入以避免重复 Cookie。
        """
        bm = getattr(self, "_browser_manager", None)
        if bm is not None and getattr(bm, "_persistent", False):
            return True  # persistent context auto-manages cookies
        cookies = self._cookie_manager.load(self.PLATFORM)
        if cookies:
            await context.add_cookies(cookies)
            return True
        return False

    def has_cookies(self) -> bool:
        """Check if saved cookies exist for this platform.

        Persistent 模式：如果 user_data_dir 目录存在且有内容，
        视为有有效 Cookie（浏览器 profile 自动管理）。
        """
        bm = getattr(self, "_browser_manager", None)
        if bm is not None and getattr(bm, "_persistent", False):
            from pathlib import Path

            user_data_dir = Path(bm._user_data_dir)
            if user_data_dir.exists() and any(user_data_dir.iterdir()):
                return True
        return self._cookie_manager.exists(self.PLATFORM)

    # ── Login detection ───────────────────────────────────────

    async def check_login(self) -> bool:
        """检测当前 Cookie 是否仍然有效。

        默认返回 False 并记录警告日志。
        子类应覆盖此方法以实现平台特定的登录检测逻辑。
        """
        logger.warning("[{}] login check not implemented", self.PLATFORM)
        return False

    async def login(self) -> bool:
        """Open a visible browser for manual login, then save cookies.

        Subclasses may override to add platform-specific login flow.
        """
        logger.info("[{}] Opening browser for manual login...", self.PLATFORM)
        context = await self._new_context()
        page = await context.new_page()
        await page.goto(self.BASE_URL, wait_until="domcontentloaded")

        logger.info("[{}] Please complete login in the browser window.", self.PLATFORM)
        input(f"  Press Enter after login on {self.PLATFORM}...")

        await self.save_cookies(context)
        await context.close()
        return True

    # ── Retry wrapper ─────────────────────────────────────────

    async def _with_retry(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute an async function with configurable retry.

        On failure, waits ``settings.crawler_retry_delay`` seconds before retrying.
        Uses ``settings.crawler_retry_times`` for max attempts (fallback to ``crawler_retry``).

        Retries on:
        - Network exceptions
        - Page load failures (PlaywrightError)
        - Timeout errors (PlaywrightTimeout)
        """
        max_retries = getattr(
            self._settings, "crawler_retry_times", self._settings.crawler_retry
        )
        delay = getattr(self._settings, "crawler_retry_delay", 5)
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    "[{}] Attempt {}/{} failed: {}",
                    self.PLATFORM,
                    attempt,
                    max_retries,
                    e,
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]

    # ── Crawl interface (template method) ─────────────────────

    async def crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """采集入口 — 自动重试 + 日志记录。

        子类应实现 ``_do_crawl`` 而非覆盖此方法。
        """
        from app.services.metrics.service import MetricsService

        start = datetime.now()
        logger.info(
            "{}:\nkeyword={}\npages={}",
            self.PLATFORM,
            keyword,
            max_pages,
        )

        try:
            products = await self._with_retry(
                self._do_crawl, keyword=keyword, max_pages=max_pages
            )
        except Exception as e:
            logger.error("[{}] Crawl failed after all retries: {}", self.PLATFORM, e)
            products = []

        elapsed = (datetime.now() - start).total_seconds()

        # Update metrics
        MetricsService.observe_crawl_duration(elapsed)
        if products:
            MetricsService.inc_crawl_success()
        else:
            MetricsService.inc_crawl_failed()

        logger.info(
            "{}:\nkeyword={}\nsuccess={}\nfailed={}\n耗时={:.1f}s",
            self.PLATFORM,
            keyword,
            len(products),
            0,
            elapsed,
        )
        return products

    @abstractmethod
    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """子类实现：实际采集逻辑。"""

    @abstractmethod
    async def _parse_product(self, element: Any) -> RawProduct | None:
        """Parse a single product card element into RawProduct."""

    # ── Utilities ─────────────────────────────────────────────

    async def _scroll_page(self, page: Page, times: int = 3, delay_ms: int = 2000) -> None:
        """Scroll the page down *times* with a delay between each scroll."""
        for _ in range(times):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(delay_ms)

    @staticmethod
    def parse_count(text: str) -> int:
        """Parse human-readable Chinese count strings.

        Examples::

            "1.2万"  -> 12000
            "3.5万"  -> 35000
            "3.5w"   -> 35000
            "100"   -> 100
            ""      -> 0
        """
        text = text.strip()
        if not text:
            return 0
        if "亿" in text:
            num = re.search(r"([\d.]+)", text)
            return int(float(num.group(1)) * 100_000_000) if num else 0
        if "万" in text or "w" in text or "W" in text:
            num = re.search(r"([\d.]+)", text)
            return int(float(num.group(1)) * 10_000) if num else 0
        num = re.search(r"\d+", text)
        return int(num.group()) if num else 0
