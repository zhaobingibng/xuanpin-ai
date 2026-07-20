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
            log_id = None
            crawl_start = datetime.now()
            try:
                products = await manager.crawl(platform, keyword=keyword, max_pages=max_pages)
                all_raw.extend(products)
                logger.info("[Job:{}] {} / {}: {} products", job_id, platform, keyword, len(products))

                # Record crawl log
                if save_to_db:
                    try:
                        from app.database.base import get_async_session_factory
                        from app.database.crawl_log_repository import CrawlLogRepository
                        from app.models.crawl_log import CrawlLog

                        session_factory = get_async_session_factory()
                        async with session_factory() as session:
                            log_repo = CrawlLogRepository(session)
                            log_record = CrawlLog(
                                keyword=keyword,
                                platform=platform,
                                total=len(products),
                                success=len(products),
                                failed=0,
                                status="SUCCESS",
                            )
                            await log_repo.create(log_record)
                    except Exception as log_e:
                        logger.warning("[Job:{}] Failed to record crawl log: {}", job_id, log_e)

            except Exception as e:
                error_msg = f"{platform}/{keyword}: {e}"
                logger.error("[Job:{}] Crawl error: {}", job_id, error_msg)
                result["errors"].append(error_msg)

                # Record failed crawl log
                if save_to_db:
                    try:
                        from app.database.base import get_async_session_factory
                        from app.database.crawl_log_repository import CrawlLogRepository
                        from app.models.crawl_log import CrawlLog

                        session_factory = get_async_session_factory()
                        async with session_factory() as session:
                            log_repo = CrawlLogRepository(session)
                            log_record = CrawlLog(
                                keyword=keyword,
                                platform=platform,
                                total=0,
                                success=0,
                                failed=1,
                                status="FAILED",
                                error=str(e),
                            )
                            await log_repo.create(log_record)
                    except Exception as log_e:
                        logger.warning("[Job:{}] Failed to record error log: {}", job_id, log_e)

    result["raw_count"] = len(all_raw)
    logger.info("[Job:{}] Total raw products: {}", job_id, len(all_raw))

    # ── Record status: RUNNING ─────────────────────────────────
    status_id = None
    if save_to_db:
        try:
            from app.database.base import get_async_session_factory
            from app.database.crawler_status_repository import CrawlerStatusRepository
            from app.models.crawler_status import CrawlerStatus

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = CrawlerStatusRepository(session)
                status_record = CrawlerStatus(
                    platform="daily_crawl",
                    status="RUNNING",
                    total=0,
                )
                created = await repo.create(status_record)
                status_id = created.id
        except Exception as e:
            logger.warning("[Job:{}] Failed to record RUNNING status: {}", job_id, e)

    if not all_raw:
        # Update status to SUCCESS (nothing to process)
        if status_id is not None:
            try:
                from app.database.base import get_async_session_factory
                from app.database.crawler_status_repository import CrawlerStatusRepository

                session_factory = get_async_session_factory()
                async with session_factory() as session:
                    repo = CrawlerStatusRepository(session)
                    await repo.update_status(status_id, status="SUCCESS", message="No products crawled")
            except Exception as e:
                logger.warning("[Job:{}] Failed to update status: {}", job_id, e)
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
            from app.services.product_service import ProductService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                svc = ProductService(session)
                save_result = await svc.save_raw_products(all_raw)
                result["saved_count"] = save_result["saved_count"]
                result["cleaned_count"] = save_result["cleaned_count"]
                result["new_count"] = save_result["new_count"]
                result["updated_count"] = save_result["updated_count"]
                result["history_count"] = save_result["history_count"]
                result["failed_save_count"] = save_result["failed_count"]
        except Exception as e:
            error_msg = f"DB save error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 5: Generate daily report ─────────────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 5: Generating daily report…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.report.daily_report import DailyReportService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                report_svc = DailyReportService(session)
                report = await report_svc.generate_and_save()
                result["report_date"] = report["date"]
                result["report_total"] = report["total"]
        except Exception as e:
            error_msg = f"Report generation error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 5b: LLM report summary (optional) ────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 5b: LLM report summary…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.database.report_repository import ReportRepository
            from app.services.ai_analysis.report_summarizer import LLMReportSummarizer

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                report_repo = ReportRepository(session)
                report = await report_repo.get_latest()
                if report:
                    summarizer = LLMReportSummarizer()
                    summary = await summarizer.summarize(report)
                    if summary:
                        result["llm_report_summary"] = summary.get("summary", "")[:200]
                        logger.info("[Job:{}] LLM report summary: {}", job_id, result["llm_report_summary"][:50])
                    else:
                        logger.debug("[Job:{}] LLM report summary skipped (unavailable)", job_id)
        except Exception as e:
            # LLM 失败不影响其他步骤
            logger.debug("[Job:{}] LLM report summary error: {}", job_id, e)

    # ── Step 6: Generate daily recommendation ──────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 6: Generating daily recommendation…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.recommendation.daily_recommendation import (
                DailyRecommendationService,
            )

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                rec_svc = DailyRecommendationService(session)
                rec = await rec_svc.generate()
                result["recommendation_total"] = rec["total"]
        except Exception as e:
            error_msg = f"Recommendation generation error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 7: Review past recommendations ────────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 7: Reviewing past recommendations…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.review.analyzer import RecommendationReviewService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                review_svc = RecommendationReviewService(session)
                review = await review_svc.review_daily()
                result["review_total"] = review["total"]
                result["review_accuracy"] = review["accuracy"]
        except Exception as e:
            error_msg = f"Review error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 8: Model learning optimization ────────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 8: Learning optimization…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.learning.optimizer import ScoringOptimizer

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                optimizer = ScoringOptimizer(session)
                opt_result = await optimizer.optimize()
                result["learning_version"] = opt_result.get("new_version")
        except Exception as e:
            error_msg = f"Learning error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 9: Knowledge building (tag learning) ──────────────
    if save_to_db:
        logger.info("[Job:{}] Step 9: Building knowledge base…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.knowledge.builder import KnowledgeBuilder

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                builder = KnowledgeBuilder(session)
                kb_result = await builder.learn_from_reviews()
                result["knowledge_processed"] = kb_result.get("processed", 0)
                result["knowledge_bindings"] = kb_result.get("bindings", 0)
        except Exception as e:
            error_msg = f"Knowledge error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 10: Strategy generation for top products ──────────
    if save_to_db:
        logger.info("[Job:{}] Step 10: Generating strategies for top products…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.database.report_repository import ReportRepository
            from app.services.strategy.generator import ProductStrategyGenerator

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                report_repo = ReportRepository(session)
                report = await report_repo.get_latest()
                if report and report.items:
                    generator = ProductStrategyGenerator(session)
                    count = 0
                    for item in report.items[:3]:
                        product_info = {
                            "product_id": item.product_id,
                            "name": item.name,
                            "price": item.price,
                            "sales_24h": 100,
                            "trend_score": 75.0,
                            "lifecycle": "HOT",
                            "knowledge_tags": [],
                        }
                        await generator.generate(product_info)
                        count += 1
                    result["strategy_generated"] = count
        except Exception as e:
            error_msg = f"Strategy error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Step 10b: LLM product analysis (optional) ─────────────
    if save_to_db:
        logger.info("[Job:{}] Step 10b: LLM product analysis…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.database.product_repository import ProductRepository
            from app.services.ai_analysis.product_analyzer import LLMProductAnalyzer
            from sqlalchemy import select
            from app.models.product import Product

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                # 获取 TOP 3 商品（按 ai_score 排序）
                stmt = select(Product).where(Product.status == "ACTIVE").order_by(Product.ai_score.desc()).limit(3)
                query_result = await session.execute(stmt)
                top_products = list(query_result.scalars().all())

                if top_products:
                    analyzer = LLMProductAnalyzer()
                    llm_analyses = []
                    for product in top_products:
                        analysis = await analyzer.analyze(product)
                        if analysis:
                            llm_analyses.append({
                                "product_id": product.id,
                                "name": product.name,
                                "summary": analysis.get("summary", "")[:100],
                                "recommendation": analysis.get("recommendation", "WATCH"),
                            })
                    if llm_analyses:
                        result["llm_product_analyses"] = llm_analyses
                        logger.info("[Job:{}] LLM analyzed {} products", job_id, len(llm_analyses))
                    else:
                        logger.debug("[Job:{}] LLM product analysis skipped (unavailable)", job_id)
        except Exception as e:
            # LLM 失败不影响其他步骤
            logger.debug("[Job:{}] LLM product analysis error: {}", job_id, e)

    # ── Step 11: Archive stale products ───────────────────────
    if save_to_db:
        logger.info("[Job:{}] Step 11: Archiving stale products…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.database.product_repository import ProductRepository

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = ProductRepository(session)
                archived = await repo.archive_stale(days=30)
                await session.commit()
                result["archived_count"] = archived
        except Exception as e:
            error_msg = f"Archive error: {e}"
            logger.error("[Job:{}] {}", job_id, error_msg)
            result["errors"].append(error_msg)

    # ── Update status: SUCCESS / FAILED ───────────────────────
    if status_id is not None:
        try:
            from app.database.base import get_async_session_factory
            from app.database.crawler_status_repository import CrawlerStatusRepository

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = CrawlerStatusRepository(session)
                final_status = "FAILED" if result["errors"] else "SUCCESS"
                await repo.update_status(
                    status_id,
                    status=final_status,
                    total=result["raw_count"],
                    success=result["saved_count"],
                    failed=result["raw_count"] - result["saved_count"],
                    message="; ".join(result["errors"]) if result["errors"] else None,
                )
        except Exception as e:
            logger.warning("[Job:{}] Failed to update final status: {}", job_id, e)

    await manager.close_all()
    result["finished_at"] = datetime.now().isoformat()

    duration = (datetime.now() - start_time).total_seconds()

    # ── Data quality metrics ──────────────────────────────────
    raw_count = result["raw_count"]
    cleaned_count = result.get("cleaned_count", 0)
    saved_count = result.get("saved_count", 0)
    result["clean_rate"] = round(cleaned_count / raw_count, 3) if raw_count > 0 else 0.0
    result["save_rate"] = round(saved_count / cleaned_count, 3) if cleaned_count > 0 else 0.0

    logger.info(
        "[Job:{}] Completed in {:.1f}s — {} raw, {} cleaned, {} saved, clean_rate={}, save_rate={}",
        job_id, duration, raw_count, cleaned_count, saved_count,
        result["clean_rate"], result["save_rate"],
    )

    return result


async def daily_pipeline_job(
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
    max_pages: int = 3,
) -> dict:
    """每日 Pipeline 定时任务入口。

    调用 DailyPipeline.run_daily() 执行完整的
    采集 → 清洗 → 保存 → 趋势分析 → 排行榜更新 流程。

    Args:
        keywords: 搜索关键词，None 使用默认列表。
        platforms: 平台列表，None 使用全部平台。
        max_pages: 每个关键词每个平台最大页数。

    Returns:
        Pipeline 执行结果摘要。
    """
    from app.tasks.pipeline import DailyPipeline

    return await DailyPipeline.run_daily(
        keywords=keywords,
        platforms=platforms,
        max_pages=max_pages,
    )


async def auto_crawl_job() -> dict:
    """自动采集任务 — 从配置读取参数，调用 daily_crawl_job。

    作为 scheduler 的默认定时任务入口。
    采集失败不会抛出异常，确保 scheduler 继续运行。

    Returns:
        daily_crawl_job 执行结果摘要。
    """
    from app.config.settings import get_settings

    settings = get_settings()
    try:
        return await daily_crawl_job(
            keywords=settings.crawl_keywords,
            platforms=settings.crawl_platforms,
            save_to_db=True,
        )
    except Exception as e:
        logger.error("auto_crawl_job 异常: {}", e)
        return {"errors": [str(e)], "saved_count": 0}
