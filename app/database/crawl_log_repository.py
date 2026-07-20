"""CrawlLog repository — persist and query crawl task history."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl_log import CrawlLog


class CrawlLogRepository:
    """采集日志数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create(self, log: CrawlLog) -> CrawlLog:
        """插入新的采集日志记录。"""
        self._session.add(log)
        await self._session.flush()
        return log

    # ── Update ────────────────────────────────────────────────

    async def update_status(
        self,
        log_id: int,
        *,
        status: str,
        total: int = 0,
        success: int = 0,
        failed: int = 0,
        error: str | None = None,
    ) -> CrawlLog | None:
        """更新采集日志状态。"""
        row = await self._session.get(CrawlLog, log_id)
        if row is None:
            return None
        row.status = status
        row.total = total
        row.success = success
        row.failed = failed
        row.error = error
        row.end_time = datetime.utcnow()
        await self._session.flush()
        return row

    # ── Query ─────────────────────────────────────────────────

    async def get_logs(
        self,
        limit: int = 20,
        platform: str | None = None,
    ) -> Sequence[CrawlLog]:
        """获取最近的采集日志记录。

        Args:
            limit: 最多返回条数。
            platform: 可选平台过滤。
        """
        stmt = select(CrawlLog).order_by(CrawlLog.start_time.desc())
        if platform:
            stmt = stmt.where(CrawlLog.platform == platform)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()
