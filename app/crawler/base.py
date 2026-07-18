"""Abstract base crawler with shared Playwright browser management."""

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config.settings import get_settings
from app.crawler.models.schemas import RawProduct


class BaseCrawler(ABC):
    """Base class for all platform crawlers.

    Provides shared browser lifecycle, cookie persistence,
    and common parsing utilities.  Subclasses implement
    platform-specific crawling and element parsing.
    """

    PLATFORM: str = ""
    BASE_URL: str = ""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._cookies_dir = Path(self._settings.crawler_cookie_dir)
        self._cookies_dir.mkdir(parents=True, exist_ok=True)

    # ── Browser lifecycle ─────────────────────────────────────

    async def _get_browser(self) -> Browser:
        """Launch Playwright and a Chromium browser (reuses if already open)."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(
                headless=self._settings.crawler_headless,
            )
        return self._browser

    async def _new_context(self) -> BrowserContext:
        """Create a new browser context with mobile-like settings."""
        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent=self._settings.crawler_user_agent,
            viewport={"width": 375, "height": 812},
            locale="zh-CN",
        )
        return context

    async def close(self) -> None:
        """Close browser and stop Playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ── Cookie management ─────────────────────────────────────

    @property
    def _cookie_file(self) -> Path:
        return self._cookies_dir / f"{self.PLATFORM}.json"

    async def save_cookies(self, context: BrowserContext) -> None:
        """Persist browser cookies to a JSON file."""
        cookies = await context.cookies()
        self._cookie_file.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[{}] Cookies saved → {}", self.PLATFORM, self._cookie_file)

    async def load_cookies(self, context: BrowserContext) -> bool:
        """Load cookies from file into the context. Return False if none."""
        if not self._cookie_file.exists():
            return False
        cookies = json.loads(self._cookie_file.read_text(encoding="utf-8"))
        if cookies:
            await context.add_cookies(cookies)
            logger.info("[{}] Loaded {} cookies", self.PLATFORM, len(cookies))
            return True
        return False

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Open a visible browser for manual login, then save cookies.

        Subclasses may override to add platform-specific login flow.
        """
        logger.info("[{}] Opening browser for manual login…", self.PLATFORM)
        context = await self._new_context()
        page = await context.new_page()
        await page.goto(self.BASE_URL, wait_until="domcontentloaded")

        logger.info("[{}] Please complete login in the browser window.", self.PLATFORM)
        input(f"  按回车键继续 (Press Enter after login on {self.PLATFORM})…")

        await self.save_cookies(context)
        await context.close()
        return True

    def has_cookies(self) -> bool:
        """Check if saved cookies exist for this platform."""
        return self._cookie_file.exists()

    # ── Abstract interface ────────────────────────────────────

    @abstractmethod
    async def crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """Crawl products matching *keyword*. Return raw parsed data."""

    @abstractmethod
    async def _parse_product(self, element) -> RawProduct | None:
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

            "1.2万"  → 12000
            "3.5万"  → 35000
            "100"   → 100
            ""      → 0
        """
        text = text.strip()
        if not text:
            return 0
        if "亿" in text:
            num = re.search(r"([\d.]+)", text)
            return int(float(num.group(1)) * 100_000_000) if num else 0
        if "万" in text:
            num = re.search(r"([\d.]+)", text)
            return int(float(num.group(1)) * 10_000) if num else 0
        num = re.search(r"\d+", text)
        return int(num.group()) if num else 0
