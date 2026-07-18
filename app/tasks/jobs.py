"""Scheduled job functions — crawl → clean → score → save pipeline."""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from app.ai.analyzer import ProductAnalyzer
from app.crawler import CrawlerManager, DouyinCrawler, KuaishouCrawler, XiaohongshuCrawler
from app.crawler.models.schemas import RawProduct
from app.services.cleaner.pipeline import ProductCleanPipeline

# Platform → Crawler class mapping
PLATFORM_CRAWLERS = {
    "xiaohongshu": XiaohongshuCrawler,
    "douyin": DouyinCrawler,
    "kuaishou": KuaishouCrawler,
}


async def daily_crawl_job(
    keywords: list[str],
    platforms: list[str] | None = None,
    max_pages: int = 3,
    save_to_db: bool = True,
) -> dict:
    """Run the full product analysis pipeline.

    This is the main scheduled job: crawl → clean → score → save.

    Args:
        keywords: list of search keywords
        platforms: platforms to crawl (None = all)
        max_pages: max pages per platform per keyword
        save_to_db: whether to persist results to database

    Returns:
        dict with job execution summary
    """
    start_time = datetime.now()
    job_id = start_time.strftime("%Y%m%d_%H%M%S")
    platforms = platforms or list(PLATFORM_CRAWLERS.keys())

    logger.info("[Job:{}] Starting daily crawl — keywords={}, platforms={}", job_id, keywords, platforms)

    result = {
        "job_id": job_id,
        "started_at": start_time.isoformat(),
        "keywords": keywords,
        "platforms": platforms,
        "raw_count": 0,
        "cleaned_count": 0,
        "saved_count": 0,
        "top_products": [],
        "errors": [],
    }

    # ── Step 1: Crawl ─────────────────────────────────────────
    logger.info("[Job:{}] Step 1: Crawling…", job_id)
    manager = CrawlerManager()
    for platform in platforms:
        cls = PLATFORM_CRAWLERS.get(platform)
        if cls:
            manager.register(cls())

    all_raw: list[RawProduct] = []
    for keyword in keywords:
        for platform in platforms:
            try:
                products = await manager.crawl(platform, keyword=keyword, max_pages=max_pages)
                all_raw.extend(products)
                logger.info("[Job:{}] {} / {}: {} products", job_id, platform, keyword, len(products))
            except Exception as e:
                error_msg = f"{platform}/{keyword}: {e}"
                logger.error("[Job:{}] Crawl error: {}", job_id, error_msg)
                result["errors"].append(error_msg)

    result["raw_count"] = len(all_raw)
    logger.info("[Job:{}] Total raw products: {}", job_id, len(all_raw))

    if not all_raw:
        logger.warning("[Job:{}] No products crawled, skipping pipeline", job_id)
        await manager.close_all()
        result["finished_at"] = datetime.now().isoformat()
        return result

    # ── Step 2: Clean ─────────────────────────────────────────
    logger.info("[Job:{}] Step 2: Cleaning…", job_id)
    pipeline = ProductCleanPipeline()
    cleaned = pipeline.process_batch(all_raw)
    result["cleaned_count"] = len(cleaned)
    logger.info("[Job:{}] Cleaned: {}/{}", job_id, len(cleaned), len(all_raw))

    # ── Step 3: Score ─────────────────────────────────────────
    logger.info("[Job:{}] Step 3: Scoring…", job_id)
    analyzer = ProductAnalyzer()
    ranked = analyzer.rank(cleaned)

    # Record top 5
    for item in ranked[:5]:
        p = item["product"]
        result["top_products"].append({
            "name": p.name,
            "platform": p.platform,
            "price": p.price,
            "ai_score": item["ai_score"],
        })

    # ── Step 4: Save ──────────────────────────────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 4: Saving to database…", job_id)
        try:
            from app.database.base import get_async_session_factory

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                saved = await manager.save_to_db(all_raw, session)
                result["saved_count"] = saved
        except Exception as e:
            error_msg = f"DB save error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    await manager.close_all()
    result["finished_at"] = datetime.now().isoformat()

    duration = (datetime.now() - start_time).total_seconds()
    logger.info("[Job:{}] Completed in {:.1f}s — {} raw, {} cleaned, {} saved",
                job_id, duration, result["raw_count"], result["cleaned_count"], result["saved_count"])

    return result
