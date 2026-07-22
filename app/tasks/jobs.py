"""Scheduled job functions — crawl → clean → score → save pipeline."""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from app.ai.analyzer import ProductAnalyzer
from app.crawler import CrawlerManager, DouyinCrawler, KuaishouCrawler, TaobaoCrawler, XiaohongshuCrawler
from app.crawler.models.schemas import RawProduct
from app.services.cleaner.pipeline import ProductCleanPipeline

# Platform → Crawler class mapping
PLATFORM_CRAWLERS = {
    "xiaohongshu": XiaohongshuCrawler,
    "douyin": DouyinCrawler,
    "kuaishou": KuaishouCrawler,
    "taobao": TaobaoCrawler,
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
            from app.services.product_scoring import ProductScoringService

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

                # Step 4b: Save ai_score + ProductScore for each saved product
                scoring_svc = ProductScoringService()
                scored_count = 0
                for product in save_result.get("saved_products", []):
                    score_record = scoring_svc.create_score_record(product)
                    product.ai_score = score_record.total_score
                    session.add(score_record)
                    scored_count += 1
                await session.commit()
                for product in save_result.get("saved_products", []):
                    await session.refresh(product)
                result["scored_count"] = scored_count
                logger.info(
                    "[Job:{}] Scored {} products (ai_score + ProductScore)",
                    job_id, scored_count,
                )
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

    # ── Step 11b: Shop scan — crawl registered shops (Phase 15) ──
    if save_to_db and "taobao" in platforms:
        logger.info("[Job:{}] Step 11b: Shop scan (registered taobao shops)…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.shop_service import ShopService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                shop_svc = ShopService(session)
                shops = await shop_svc.get_shops_needing_scan(platform="taobao")
                scanned_ids: list[int] = []
                shop_product_count = 0

                if shops:
                    crawler = TaobaoCrawler()
                    try:
                        for shop in shops:
                            shop_url = shop.shop_url or f"https://shop{shop.shop_id}.taobao.com"
                            try:
                                prods = await crawler.crawl_shop(
                                    shop_url=shop_url,
                                    shop_name=shop.shop_name,
                                    max_pages=2,
                                    limit=30,
                                )
                                shop_product_count += len(prods)
                                all_raw.extend(prods)
                                scanned_ids.append(shop.id)
                                logger.info(
                                    "[Job:{}] Shop '{}': {} products",
                                    job_id, shop.shop_name, len(prods),
                                )
                            except Exception as e:
                                logger.warning(
                                    "[Job:{}] Shop '{}' crawl error: {}",
                                    job_id, shop.shop_name, e,
                                )
                    finally:
                        await crawler.close()

                    if scanned_ids:
                        await shop_svc.batch_mark_scanned(scanned_ids)

                result["shops_crawled"] = len(scanned_ids)
                result["shop_products"] = shop_product_count
                logger.info(
                    "[Job:{}] Shop scan complete: {}/{} shops, {} products",
                    job_id, len(scanned_ids), len(shops), shop_product_count,
                )
        except Exception as e:
            logger.debug("[Job:{}] Shop scan error: {}", job_id, e)

    # ── Step 11c: Shop discovery — auto-discover high-value shops (Phase 15) ──
    if save_to_db and "taobao" in platforms and all_raw:
        logger.info("[Job:{}] Step 11c: Shop discovery (auto-discover high-value shops)…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.discovery.shop_discovery import ShopDiscoveryService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                discovery = ShopDiscoveryService(session)
                scored_shops = await discovery.discover_from_products(
                    all_raw, auto_register=True, min_score=40.0
                )
                result["shops_discovered"] = len(scored_shops)
                if scored_shops:
                    result["top_discovered_shops"] = [
                        {"name": s.shop_name, "score": s.score, "products": s.stats.product_count}
                        for s in scored_shops[:5]
                    ]
                logger.info(
                    "[Job:{}] Shop discovery: {} shops scored",
                    job_id, len(scored_shops),
                )
        except Exception as e:
            logger.debug("[Job:{}] Shop discovery error: {}", job_id, e)

    # ── Step 12: New product detection (Phase 14) ─────────────
    if save_to_db:
        logger.info("[Job:{}] Step 12: New product detection…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.discovery.new_product_detector import NewProductDetector

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                detector = NewProductDetector(session)
                detection = await detector.detect_all_enabled_shops(platform="taobao")
                result["new_products_detected"] = detection["total_new_products"]
                result["shops_scanned"] = detection["total_shops"]
                logger.info(
                    "[Job:{}] New products: {} from {} shops",
                    job_id, detection["total_new_products"], detection["total_shops"],
                )
        except Exception as e:
            # 新品检测失败不影响其他步骤
            logger.debug("[Job:{}] New product detection error: {}", job_id, e)

    # ── Step 13: Supply chain matching (Phase 14) ─────────────
    if save_to_db:
        logger.info("[Job:{}] Step 13: Supply chain matching…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.database.product_repository import ProductRepository
            from app.services.supplier_matching import SupplierMatchingService
            from app.config.scheduler import scheduler_settings

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = ProductRepository(session)
                new_products = await repo.find_new_products(limit=100)
                match_svc = SupplierMatchingService()
                total_matched = 0
                match_errors = 0
                for product in new_products:
                    try:
                        matches = await match_svc.match_products_with_matcher(
                            session, product, top_k=3,
                        )
                        if matches:
                            for m in matches:
                                session.add(m)
                            total_matched += 1
                    except Exception as inner_e:
                        match_errors += 1
                        logger.warning(
                            "[Job:{}] Match failed product_id={}: {}",
                            job_id, product.id, inner_e,
                        )
                await session.commit()
                result["matched_products"] = total_matched
                result["match_errors"] = match_errors
                logger.info(
                    "[Job:{}] Matched {} products ({} errors)",
                    job_id, total_matched, match_errors,
                )
        except Exception as e:
            logger.debug("[Job:{}] Supply chain matching error: {}", job_id, e)
    # ── Step 14: Daily selection report (Phase 16) ────────────
    if save_to_db:
        logger.info("[Job:{}] Step 14: Daily selection report…", job_id)
        try:
            from app.database.base import get_async_session_factory
            from app.services.report.daily_selection_report import DailySelectionReportService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                report_svc = DailySelectionReportService(session)
                daily_report = await report_svc.generate(limit=20)
                result["daily_report_summary"] = daily_report["summary"]
                result["daily_report_date"] = daily_report["date"]
                logger.info(
                    "[Job:{}] Daily report: {} new products, {} matches, avg margin {:.1f}%",
                    job_id,
                    daily_report["summary"]["new_products_count"],
                    daily_report["summary"]["matched_count"],
                    daily_report["summary"]["avg_profit_margin"],
                )
        except Exception as e:
            # 日报生成失败不影响其他步骤
            logger.debug("[Job:{}] Daily selection report error: {}", job_id, e)

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
    """Daily pipeline job -- deprecated, kept for import compatibility."""
    from app.tasks.crawler_jobs import crawl_all_platforms

    raw = await crawl_all_platforms(
        keywords=keywords, platforms=platforms, max_pages=max_pages,
    )
    return {
        "status": "deprecated",
        "raw_count": len(raw),
        "cleaned_count": 0,
        "message": "Use `python -m app.cli daily` instead",
    }


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
