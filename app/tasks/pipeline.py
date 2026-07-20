"""Daily pipeline — orchestrates crawl → clean → save → trend → ranking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from app.tasks.crawler_jobs import crawl_all_platforms


class DailyPipeline:
    """每日数据处理 Pipeline。

    串联：采集 → 清洗 → 保存 → 趋势分析 → 排行榜更新。

    Usage::

        result = await DailyPipeline.run_daily()
        # {"raw_count": 50, "cleaned_count": 45, ...}
    """

    @staticmethod
    async def run_daily(
        keywords: list[str] | None = None,
        platforms: list[str] | None = None,
        max_pages: int = 3,
    ) -> dict[str, Any]:
        """执行完整的每日 Pipeline。

        Args:
            keywords: 搜索关键词，None 使用默认列表。
            platforms: 平台列表，None 使用全部平台。
            max_pages: 每个关键词每个平台最大页数。

        Returns:
            Pipeline 执行结果摘要。
        """
        start_time = datetime.now()
        logger.info("开始每日采集")

        summary: dict[str, Any] = {
            "started_at": start_time.isoformat(),
            "raw_count": 0,
            "cleaned_count": 0,
            "saved_count": 0,
            "history_count": 0,
            "trend_count": 0,
            "errors": [],
        }

        # ── Step 1: 采集 ────────────────────────────────────────
        try:
            raw_products = await crawl_all_platforms(
                keywords=keywords,
                platforms=platforms,
                max_pages=max_pages,
            )
            summary["raw_count"] = len(raw_products)
            logger.info("采集数量: {}", len(raw_products))
        except Exception as e:
            logger.error("采集步骤异常: {}", e)
            summary["errors"].append(f"crawl: {e}")
            summary["finished_at"] = datetime.now().isoformat()
            return summary

        # ── Step 2–5: 清洗 → 保存 → 趋势 → 排行榜 ──────────────
        if not raw_products:
            logger.info("空数据，跳过后续步骤")
            duration = (datetime.now() - start_time).total_seconds()
            summary["finished_at"] = datetime.now().isoformat()
            summary["duration_seconds"] = round(duration, 2)
            return summary

        try:
            from app.database.base import get_async_session_factory
            from app.tasks.analysis_jobs import analyze_products

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                analysis_result = await analyze_products(raw_products, session)

            summary["cleaned_count"] = analysis_result.get("cleaned_count", 0)
            summary["saved_count"] = analysis_result.get("saved_count", 0)
            summary["history_count"] = analysis_result.get("history_count", 0)
            summary["trend_count"] = analysis_result.get("trend_count", 0)
        except Exception as e:
            logger.error("分析步骤异常: {}", e)
            summary["errors"].append(f"analysis: {e}")

        # ── 完成 ────────────────────────────────────────────────
        duration = (datetime.now() - start_time).total_seconds()
        summary["finished_at"] = datetime.now().isoformat()
        summary["duration_seconds"] = round(duration, 2)

        logger.info(
            "Pipeline 完成: {}s, raw={}, cleaned={}, saved={}, trend={}",
            summary["duration_seconds"],
            summary["raw_count"],
            summary["cleaned_count"],
            summary["saved_count"],
            summary["trend_count"],
        )

        return summary
