"""Crawler status repository — persist and query crawler execution records."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawler_status import CrawlerStatus


class CrawlerStatusRepository:
    """采集状态数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create(self, status: CrawlerStatus) -> CrawlerStatus:
        """插入新的采集状态记录。"""
        self._session.add(status)
        await self._session.flush()
        return status

    # ── Update ────────────────────────────────────────────────

    async def update_status(
        self,
        status_id: int,
        *,
        status: str,
        total: int = 0,
        success: int = 0,
        failed: int = 0,
        message: str | None = None,
    ) -> CrawlerStatus | None:
        """更新已有记录的状态。"""
        row = await self._session.get(CrawlerStatus, status_id)
        if row is None:
            return None
        row.status = status
        row.total = total
        row.success = success
        row.failed = failed
        row.message = message
        await self._session.flush()
        return row

    # ── Query ─────────────────────────────────────────────────

    async def get_latest(self, limit: int = 10) -> Sequence[CrawlerStatus]:
        """获取最近的采集状态记录。"""
        stmt = (
            select(CrawlerStatus)
            .order_by(CrawlerStatus.last_run_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
