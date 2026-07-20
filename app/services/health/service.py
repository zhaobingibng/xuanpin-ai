"""HealthService — system health monitoring."""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Health status constants
SYSTEM_HEALTHY = "healthy"
SYSTEM_WARNING = "warning"
SYSTEM_ERROR = "error"


class HealthService:
    """检测系统健康状态。

    Checks:
    1. 数据库连接
    2. Crawler 状态 (最近执行记录)
    3. Scheduler 状态 (是否运行中)
    4. 最近采集时间
    """

    def __init__(self, session: AsyncSession, scheduler_running: bool = False) -> None:
        self._session = session
        self._scheduler_running = scheduler_running

    async def check(self) -> dict:
        """运行所有健康检查，返回综合状态。

        Returns:
            dict with keys: status, database, crawler, scheduler, last_crawl.
        """
        from app.services.metrics.service import MetricsService

        db_ok = await self._check_database()
        crawler_info = await self._check_crawler()
        scheduler_ok = self._scheduler_running

        # Update metrics gauges
        MetricsService.set_scheduler_running(scheduler_ok)
        MetricsService.set_crawler_running(crawler_info.get("ok", False))

        # Determine overall status
        if db_ok and scheduler_ok and crawler_info.get("ok", True):
            overall = SYSTEM_HEALTHY
        elif not db_ok:
            overall = SYSTEM_ERROR
        else:
            overall = SYSTEM_WARNING

        return {
            "status": overall,
            "database": db_ok,
            "crawler": crawler_info.get("ok", False),
            "scheduler": scheduler_ok,
            "last_crawl": crawler_info.get("last_crawl"),
        }

    async def _check_database(self) -> bool:
        """检查数据库连接是否正常。"""
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning("[Health] Database check failed: {}", e)
            return False

    async def _check_crawler(self) -> dict:
        """检查最近采集状态。"""
        try:
            from app.database.crawler_status_repository import CrawlerStatusRepository

            repo = CrawlerStatusRepository(self._session)
            records = await repo.get_latest(limit=1)

            if not records:
                return {"ok": True, "last_crawl": None}

            latest = records[0]
            last_crawl = (
                latest.last_run_time.isoformat() if latest.last_run_time else None
            )
            ok = latest.status != "FAILED"
            return {"ok": ok, "last_crawl": last_crawl}
        except Exception as e:
            logger.warning("[Health] Crawler check failed: {}", e)
            return {"ok": False, "last_crawl": None}
