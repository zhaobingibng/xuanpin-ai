"""Dashboard service — aggregate system statistics for operations management."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crawler_status_repository import CrawlerStatusRepository
from app.database.lifecycle_repository import LifecycleRepository
from app.database.report_repository import ReportRepository
from app.database.task_execution_repository import TaskExecutionRepository
from app.models.daily_report import DailyReport
from app.models.product import Product


# Global notification history (shared with NotificationService)
_notification_history: list[dict] = []


class DashboardService:
    """运营后台统计服务。

    聚合系统运行状态，提供总览数据。

    Usage::

        svc = DashboardService(session)
        overview = await svc.overview()
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._lifecycle_repo = LifecycleRepository(session)
        self._report_repo = ReportRepository(session)
        self._crawler_repo = CrawlerStatusRepository(session)
        self._task_repo = TaskExecutionRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def overview(self) -> dict[str, Any]:
        """返回系统总览数据。

        Returns:
            包含 products, today_crawl, hot_products, rising_products,
            today_recommendations, average_score, platform_distribution,
            category_distribution 的字典。
        """
        products_count = await self._count_products()
        today_crawl = await self._count_today_crawl()
        hot_products = await self._count_lifecycle("HOT")
        rising_products = await self._count_lifecycle("RISING")
        today_recs, avg_score = await self._today_recommendation_stats()
        platform_dist = await self._platform_distribution()
        category_dist = await self._category_distribution()

        return {
            "products": products_count,
            "today_crawl": today_crawl,
            "hot_products": hot_products,
            "rising_products": rising_products,
            "today_recommendations": today_recs,
            "average_score": avg_score,
            "platform_distribution": platform_dist,
            "category_distribution": category_dist,
        }

    # ── Helpers ───────────────────────────────────────────────

    async def _count_products(self) -> int:
        stmt = select(func.count(Product.id))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _count_today_crawl(self) -> int:
        today = date.today()
        stmt = select(func.count(Product.id)).where(
            func.date(Product.created_at) == today.isoformat()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _count_lifecycle(self, stage: str) -> int:
        stmt = select(func.count(Product.id)).where(
            Product.lifecycle_stage == stage
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _today_recommendation_stats(self) -> tuple[int, float]:
        today = date.today()
        report = await self._report_repo.find_by_date(today)
        if report is None:
            return 0, 0.0
        return report.total, round(report.average_score, 1)

    async def _platform_distribution(self) -> dict[str, int]:
        stmt = (
            select(Product.platform, func.count(Product.id))
            .group_by(Product.platform)
            .order_by(func.count(Product.id).desc())
        )
        result = await self._session.execute(stmt)
        return {platform: count for platform, count in result.all()}

    async def _category_distribution(self) -> dict[str, int]:
        stmt = (
            select(Product.category, func.count(Product.id))
            .where(Product.category.isnot(None))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        )
        result = await self._session.execute(stmt)
        return {category: count for category, count in result.all() if category}

    # ── System Operations ──────────────────────────────────────

    async def system_overview(self) -> dict[str, Any]:
        """返回系统运维总览数据。

        Returns:
            包含 health, uptime, task_stats, crawler_status, scheduler_status 的字典。
        """
        from app.services.health.service import HealthService
        from app.services.metrics.service import (
            MetricsService,
            SCHEDULER_TASK_TOTAL,
            SCHEDULER_TASK_FAILED_TOTAL,
        )
        from app.api.main import _scheduler_instance

        # Health check
        health_svc = HealthService(self._session, scheduler_running=_scheduler_instance is not None)
        health_result = await health_svc.check()

        # Task stats
        recent_tasks = await self._task_repo.get_recent(limit=100)
        total_tasks = len(recent_tasks)
        failed_tasks = sum(1 for t in recent_tasks if t.status == "FAILED")
        success_rate = ((total_tasks - failed_tasks) / total_tasks * 100) if total_tasks > 0 else 100.0

        # Uptime (from metrics or simple calculation)
        # For now, use a placeholder - in production, track from app startup
        uptime_seconds = 0

        return {
            "health": health_result,
            "uptime_seconds": uptime_seconds,
            "task_stats": {
                "total": total_tasks,
                "failed": failed_tasks,
                "success_rate": round(success_rate, 2),
            },
            "crawler_status": health_result.get("crawler", False),
            "scheduler_status": health_result.get("scheduler", False),
        }

    async def get_recent_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近任务执行记录。

        Args:
            limit: 返回记录数量限制。

        Returns:
            任务记录列表。
        """
        tasks = await self._task_repo.get_recent(limit=limit)
        return [
            {
                "id": t.id,
                "task_name": t.task_name,
                "start_time": t.start_time.isoformat() if t.start_time else None,
                "end_time": t.end_time.isoformat() if t.end_time else None,
                "status": t.status,
                "duration": t.duration,
                "error": t.error,
            }
            for t in tasks
        ]

    def get_notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取通知历史。

        Args:
            limit: 返回记录数量限制。

        Returns:
            通知记录列表。
        """
        return _notification_history[-limit:]

    def get_logs(
        self,
        log_file: str = "app.log",
        limit: int = 100,
        log_dir: str = "logs",
    ) -> list[str]:
        """读取日志文件。

        Args:
            log_file: 日志文件名 (app.log, error.log, crawler.log)。
            limit: 返回行数限制。
            log_dir: 日志目录。

        Returns:
            日志行列表（从最新开始）。
        """
        log_path = Path(log_dir) / log_file
        if not log_path.exists():
            return []

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Return last `limit` lines in reverse order (newest first)
            return [line.rstrip() for line in lines[-limit:]][::-1]
        except Exception as e:
            logger.warning("[Dashboard] Failed to read log file {}: {}", log_path, e)
            return []
