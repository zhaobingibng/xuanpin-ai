"""Crawler job — orchestrate all platform crawlers and collect raw products."""

from __future__ import annotations

import asyncio
import random

from loguru import logger

from app.config.settings import get_settings
from app.config.scheduler import scheduler_settings
from app.config.crawler import crawler_settings
from app.crawler import (
    CrawlerManager,
    DouyinCrawler,
    KuaishouCrawler,
    XiaohongshuCrawler,
)
from app.crawler.models.schemas import RawProduct

# Default search keywords for daily crawl
DEFAULT_KEYWORDS: list[str] = [
    "蓝牙耳机",
    "手机壳",
    "防晒霜",
    "水杯",
    "收纳盒",
]

# Platform → Crawler class mapping
PLATFORM_CRAWLERS = {
    "xiaohongshu": XiaohongshuCrawler,
    "douyin": DouyinCrawler,
    "kuaishou": KuaishouCrawler,
}


# ── 300012 Anti-bot Detection ─────────────────────────────────


async def _verify_xhs_300012(crawler: XiaohongshuCrawler) -> bool:
    """Verify if the Xiaohongshu session is blocked by 300012.

    Opens a lightweight probe page in the same persistent context,
    navigates to the XHS homepage, and checks if the URL is
    redirected to the 300012 error page.

    Returns True only when error_code=300012 is explicitly present
    in the page URL.  Normal 0-product results do NOT trigger this.

    Args:
        crawler: The XiaohongshuCrawler instance (must have been used
                 at least once so the persistent context is alive).
    """
    try:
        ctx = await crawler._browser_manager.new_context("xiaohongshu")
        page = await ctx.new_page()
        await page.goto(
            "https://www.xiaohongshu.com/explore",
            wait_until="domcontentloaded",
            timeout=crawler_settings.anti_bot_probe_timeout_ms,
        )
        url = page.url
        await ctx.close()  # closes probe page via _ContextProxy

        is_blocked = "error_code=300012" in url or "300012" in url
        if is_blocked:
            logger.warning(
                "[circuit-breaker] 300012 confirmed — URL: {}", url[:120]
            )
        else:
            logger.debug(
                "[circuit-breaker] 300012 probe OK — URL: {}", url[:120]
            )
        return is_blocked

    except Exception as e:
        logger.warning("[circuit-breaker] 300012 probe failed: {}", e)
        return False  # cannot confirm → assume OK


async def crawl_all_platforms(
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
    max_pages: int | None = None,
) -> list[RawProduct]:
    """执行全平台采集，返回 RawProduct 列表。

    每个平台独立 try/except，单个平台异常不会中断其他平台。

    Args:
        keywords: 搜索关键词列表，None 则使用默认关键词。
        platforms: 平台列表，None 则采集全部平台。
        max_pages: 每个关键词每个平台最大采集页数。

    Returns:
        所有平台采集到的 RawProduct 列表。
    """
    keywords = keywords or DEFAULT_KEYWORDS
    platforms = platforms or list(PLATFORM_CRAWLERS.keys())
    if max_pages is None:
        max_pages = scheduler_settings.crawl_max_pages

    logger.info(
        "开始每日采集 — keywords={}, platforms={}",
        keywords,
        platforms,
    )

    manager = CrawlerManager()
    for platform in platforms:
        cls = PLATFORM_CRAWLERS.get(platform)
        if cls:
            manager.register(cls())

    all_raw: list[RawProduct] = []
    settings = get_settings()

    # Track xiaohongshu success for 300012 circuit breaker
    xhs_had_success = False
    xhs_circuit_open = False

    for platform in platforms:
        for keyword in keywords:

            # ── Skip remaining xiaohongshu keywords if circuit breaker is open ──
            if platform == "xiaohongshu" and xhs_circuit_open:
                logger.info(
                    "[circuit-breaker] skipping {} / {} (300012 active)",
                    platform, keyword,
                )
                continue

            try:
                products = await manager.crawl(
                    platform, keyword=keyword, max_pages=max_pages
                )
                all_raw.extend(products)
                logger.info(
                    "采集完成: {} / {} → {} 条",
                    platform,
                    keyword,
                    len(products),
                )

                # ── 300012 circuit breaker (xiaohongshu only) ──
                if platform == "xiaohongshu":
                    if len(products) > 0:
                        xhs_had_success = True
                    elif xhs_had_success:
                        # Had success before but now 0 → verify 300012
                        xhs_crawler = manager._crawlers.get("xiaohongshu")
                        if xhs_crawler is not None:
                            is_300012 = await _verify_xhs_300012(xhs_crawler)
                            if is_300012:
                                xhs_circuit_open = True
                                logger.warning(
                                    "[circuit-breaker] xiaohongshu 300012 detected "
                                    "after keyword '{}'. "
                                    "Stopping remaining xiaohongshu keywords. "
                                    "Collected {} products so far.",
                                    keyword,
                                    len([p for p in all_raw if p.platform == "xiaohongshu"]),
                                )

            except Exception as e:
                logger.error(
                    "采集异常: {} / {} → {}", platform, keyword, e
                )

            # Xiaohongshu cooldown: delay between keywords to avoid rate limiting
            if platform == "xiaohongshu" and keyword != keywords[-1] and not xhs_circuit_open:
                cooldown = random.randint(
                    settings.xhs_cooldown_min,
                    settings.xhs_cooldown_max,
                )
                logger.info(
                    "[cooldown] xiaohongshu: 等待 {}s 后采集下一个关键词",
                    cooldown,
                )
                await asyncio.sleep(cooldown)

    await manager.close_all()

    logger.info("采集数量: {} 条原始数据", len(all_raw))
    return all_raw
