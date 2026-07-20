"""FailedTask repository — persist and query failed task records."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.failed_task import (
    FailedTask,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RETRYING,
)


class FailedTaskRepository:
    """失败任务数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, task: FailedTask) -> FailedTask:
        """插入新的失败任务记录。"""
        self._session.add(task)
        await self._session.flush()
        return task

    async def get_by_id(self, task_id: int) -> FailedTask | None:
        """根据 ID 获取失败任务记录。"""
        return await self._session.get(FailedTask, task_id)

    async def get_failed(self, status: str | None = None, limit: int = 50) -> Sequence[FailedTask]:
        """获取失败任务列表。

        Args:
            status: 按状态筛选 (None = 全部)
            limit: 返回数量限制
        """
        stmt = select(FailedTask).order_by(FailedTask.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(FailedTask.status == status)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_pending(self, limit: int = 50) -> Sequence[FailedTask]:
        """获取待重试的任务。"""
        stmt = (
            select(FailedTask)
            .where(FailedTask.status == STATUS_PENDING)
            .where(FailedTask.retry_count < FailedTask.max_retry)
            .order_by(FailedTask.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_status(
        self,
        task_id: int,
        status: str,
        error: str | None = None,
        increment_retry: bool = False,
    ) -> FailedTask | None:
        """更新任务状态。

        Args:
            task_id: 任务 ID
            status: 新状态
            error: 错误信息 (可选)
            increment_retry: 是否递增重试次数
        """
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        task.status = status
        task.updated_at = datetime.utcnow()
        if error is not None:
            task.error = error
        if increment_retry:
            task.retry_count += 1

        await self._session.flush()
        return task

    async def mark_retrying(self, task_id: int) -> FailedTask | None:
        """标记任务为重试中。"""
        return await self.update_status(task_id, STATUS_RETRYING, increment_retry=True)

    async def mark_resolved(self, task_id: int) -> FailedTask | None:
        """标记任务为已解决。"""
        return await self.update_status(task_id, STATUS_RESOLVED)

    async def mark_failed(self, task_id: int, error: str | None = None) -> FailedTask | None:
        """标记任务为最终失败。"""
        return await self.update_status(task_id, STATUS_FAILED, error=error)
