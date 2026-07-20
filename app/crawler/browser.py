"""BrowserManager — unified Playwright browser lifecycle management.

Enhanced with UserAgentManager, behavior simulation, and page crash recovery.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from app.config.settings import AppSettings

if TYPE_CHECKING:
    from app.crawler.base import CookieManager


# ── UserAgentManager ────────────────────────────────────────────


class UserAgentManager:
    """随机 User-Agent 管理器。

    支持 Chrome / Edge / Mobile 三种类型，
    每次启动浏览器随机选择一个以降低被反爬检测的概率。
    """

    CHROME_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    EDGE_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    ]

    MOBILE_AGENTS = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]

    @classmethod
    def get_random(cls, ua_type: str | None = None) -> str:
        """获取随机 User-Agent。

        Args:
            ua_type: 指定类型 "chrome"/"edge"/"mobile"，None 则随机选择。
        """
        pools: dict[str, list[str]] = {
            "chrome": cls.CHROME_AGENTS,
            "edge": cls.EDGE_AGENTS,
            "mobile": cls.MOBILE_AGENTS,
        }

        if ua_type and ua_type in pools:
            return random.choice(pools[ua_type])

        all_agents: list[str] = []
        for agents in pools.values():
            all_agents.extend(agents)
        return random.choice(all_agents)


# ── Behavior Simulation ─────────────────────────────────────────


async def random_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
    """随机等待一段时间，模拟人类操作间隔。"""
    delay = random.randint(min_ms, max_ms)
    await asyncio.sleep(delay / 1000)


async def random_scroll(page: Page, times: int = 3) -> None:
    """随机滚动页面，模拟浏览行为。"""
    for _ in range(times):
        distance = random.randint(300, 800)
        await page.evaluate(f"window.scrollBy(0, {distance})")
        await asyncio.sleep(random.uniform(0.3, 1.0))


async def mouse_move(page: Page) -> None:
    """模拟鼠标随机移动。"""
    x = random.randint(100, 350)
    y = random.randint(200, 700)
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.1, 0.5))


# ── BrowserManager ──────────────────────────────────────────────


class BrowserManager:
    """Manage Playwright browser lifecycle.

    Provides a single entry point for starting Playwright, creating browser
    contexts with pre-configured User-Agent / locale / viewport / cookies,
    and tearing everything down cleanly.

    Enhanced with:
    - Random User-Agent selection via UserAgentManager
    - Page crash / context closed / timeout recovery
    """

    def __init__(self, settings: AppSettings, cookie_manager: CookieManager) -> None:
        self._settings = settings
        self._cookie_manager = cookie_manager
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        self._persistent = getattr(settings, "browser_persistent", False)
        self._persistent_ctx: BrowserContext | None = None
        self._user_data_dir = getattr(settings, "browser_user_data_dir", "./storage/browser_profile")

    # ── Public API ────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Playwright 和 Chromium 浏览器。

        Persistent 模式使用 launch_persistent_context，
        保存完整浏览器状态（cookie / localStorage / IndexedDB）。
        """
        if self._playwright is not None:
            return
        self._playwright = await async_playwright().start()

        if self._persistent:
            from pathlib import Path

            Path(self._user_data_dir).mkdir(parents=True, exist_ok=True)
            self._persistent_ctx = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=self._user_data_dir,
                headless=self._settings.browser_headless,
                locale="zh-CN",
                viewport={"width": 375, "height": 812},
            )
            logger.info("Browser started (persistent: {})", self._user_data_dir)
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=self._settings.browser_headless,
            )
            logger.info("Browser started")

    async def new_context(self, platform: str) -> BrowserContext:
        """创建带完整配置的 BrowserContext 并自动加载 Cookie。

        Persistent 模式返回持久上下文的代理（close 为空操作），
        避免每次创建新 context 和手动注入 Cookie。

        使用随机 User-Agent，并在页面崩溃时自动恢复。
        """
        if self._persistent:
            if self._persistent_ctx is None:
                await self.start()
            logger.info("[{}] Using persistent context (UA: managed by profile)", platform)
            return _ContextProxy(self._persistent_ctx)  # type: ignore[arg-type]

        # ── Standard mode ──────────────────────────────────────
        if self._browser is None:
            await self.start()

        user_agent = UserAgentManager.get_random()

        context = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 375, "height": 812},
            locale="zh-CN",
        )
        self._contexts.append(context)
        logger.info("[{}] Context created (UA: {}...)", platform, user_agent[:50])

        # 通过 CookieManager 加载 Cookie
        cookies = self._cookie_manager.load(platform)
        if cookies:
            await context.add_cookies(cookies)
            logger.info("[{}] Cookie loaded ({}条)", platform, len(cookies))

        return context

    async def new_page(self, platform: str) -> Page:
        """创建新 Context 并返回一个 Page。"""
        context = await self.new_context(platform)
        return await context.new_page()

    async def safe_goto(
        self,
        page: Page,
        url: str,
        *,
        platform: str = "",
        timeout: int | None = None,
        wait_until: str = "networkidle",
    ) -> Page:
        """安全导航，支持 page crash / context closed / timeout 自动恢复。

        如果页面异常，自动重新创建 BrowserContext 并重试一次。

        Args:
            page: 当前 Page 对象。
            url: 目标 URL。
            platform: 平台名称，用于 Cookie 加载。
            timeout: 超时毫秒数，None 使用 settings.browser_timeout。
            wait_until: Playwright wait_until 参数。

        Returns:
            可用的 Page（可能是重建后的新 Page）。
        """
        timeout = timeout or self._settings.browser_timeout

        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return page
        except Exception as e:
            logger.warning(
                "[{}] Page navigation failed: {}, attempting recovery…",
                platform,
                e,
            )
            return await self._recover_page(platform, url, timeout, wait_until)

    async def _recover_page(
        self,
        platform: str,
        url: str,
        timeout: int,
        wait_until: str,
    ) -> Page:
        """页面异常恢复：关闭旧 context，重新创建并导航。"""
        from app.services.metrics.service import MetricsService

        logger.info("[{}] Recovering: creating new context…", platform)

        # Increment browser restart counter
        MetricsService.inc_browser_restart()

        try:
            context = await self.new_context(platform)
            new_page = await context.new_page()
            await new_page.goto(url, wait_until=wait_until, timeout=timeout)
            logger.info("[{}] Page recovered successfully", platform)
            return new_page
        except Exception as e:
            logger.error("[{}] Page recovery failed: {}", platform, e)
            raise

    async def close(self) -> None:
        """关闭所有 Context、Browser 和 Playwright。

        Persistent 模式：关闭持久上下文（自动保存状态到 user_data_dir），
        然后停止 Playwright。不尝试关闭 self._browser（persistent 模式下为 None）。
        """
        # ── Standard mode: close tracked contexts ──
        for ctx in self._contexts:
            try:
                await ctx.close()
            except Exception as e:
                logger.error("Failed to close context: {}", e)
        self._contexts.clear()

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.error("Failed to close browser: {}", e)
            self._browser = None

        # ── Persistent mode: close persistent context ──
        if self._persistent_ctx:
            try:
                await self._persistent_ctx.close()
            except Exception as e:
                logger.error("Failed to close persistent context: {}", e)
            self._persistent_ctx = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.error("Failed to stop Playwright: {}", e)
            self._playwright = None

        logger.info("Browser closed")


# ── _ContextProxy ─────────────────────────────────────────────


class _ContextProxy:
    """Transparent proxy for a persistent BrowserContext.

    In persistent mode a single shared BrowserContext is reused across
    all crawlers.  Crawlers typically call ``context.close()`` inside
    ``finally`` blocks; if that call reached the real context the
    persistent state would be destroyed.

    ``_ContextProxy`` wraps the real context and:
    * Makes ``close()`` a **no-op** so the persistent context stays alive.
    * Delegates **everything else** (``new_page``, ``cookies``,
      ``add_cookies``, ``goto`` …) to the underlying context unchanged.
    """

    def __init__(self, real_context: BrowserContext) -> None:
        # Use object.__setattr__ to bypass our __setattr__ proxy
        object.__setattr__(self, "_real_context", real_context)

    # ── Overridden lifecycle ─────────────────────────────────

    async def close(self) -> None:  # type: ignore[override]
        """Close all pages but keep the persistent context alive.

        Each ``context.close()`` call in a crawler's ``finally`` block
        cleans up the pages it created, preventing page accumulation
        across multiple crawl / check_login calls.  The context itself
        stays alive so the browser profile (cookies, localStorage) is
        preserved.
        """
        for page in self._real_context.pages:
            try:
                await page.close()
            except Exception:
                pass

    # ── Transparent delegation ───────────────────────────────

    def __getattr__(self, name: str):
        return getattr(self._real_context, name)

    def __setattr__(self, name: str, value):
        setattr(self._real_context, name, value)
