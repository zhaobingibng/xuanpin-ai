"""TaskExecution repository — persist and query task execution records."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_execution import TaskExecution


class TaskExecutionRepository:
    """任务执行记录数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: TaskExecution) -> TaskExecution:
        """插入新的执行记录。"""
        self._session.add(record)
        await self._session.flush()
        return record

    async def finish(
        self,
        record_id: int,
        *,
        status: str,
        duration: float | None = None,
        error: str | None = None,
    ) -> TaskExecution | None:
        """更新执行记录的完成状态。"""
        row = await self._session.get(TaskExecution, record_id)
        if row is None:
            return None
        row.status = status
        row.end_time = datetime.utcnow()
        row.duration = duration
        row.error = error
        await self._session.flush()
        return row

    async def get_recent(self, limit: int = 20) -> Sequence[TaskExecution]:
        """获取最近的执行记录。"""
        stmt = (
            select(TaskExecution)
            .order_by(TaskExecution.start_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_task(self, task_name: str, limit: int = 10) -> Sequence[TaskExecution]:
        """获取指定任务的执行记录。"""
        stmt = (
            select(TaskExecution)
            .where(TaskExecution.task_name == task_name)
            .order_by(TaskExecution.start_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
