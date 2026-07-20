"""TaskQueueService — failed task lifecycle management."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.failed_task_repository import FailedTaskRepository
from app.models.failed_task import (
    FailedTask,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RETRYING,
)

T = TypeVar("T")


class TaskQueueService:
    """失败任务队列管理服务。

    Features:
    - Auto-create FailedTask on task failure
    - Support manual and automatic retry
    - Track retry lifecycle (PENDING → RETRYING → RESOLVED/FAILED)
    - Metrics tracking
    - Notification on status changes

    Usage::

        svc = TaskQueueService(session)
        task = await svc.record_failure(
            task_name="crawl_job",
            error="Connection timeout",
            exception_type="TimeoutError",
            payload={"keyword": "test"},
        )
        result = await svc.retry_task(task.id, some_async_func)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = FailedTaskRepository(session)

    # ── Record Failure ─────────────────────────────────────────

    async def record_failure(
        self,
        task_name: str,
        error: str | None = None,
        exception_type: str | None = None,
        payload: dict[str, Any] | None = None,
        max_retry: int = 3,
    ) -> FailedTask:
        """记录失败任务。

        Args:
            task_name: 任务名称
            error: 错误信息
            exception_type: 异常类型
            payload: 任务参数 (JSON serializable)
            max_retry: 最大重试次数

        Returns:
            Created FailedTask record.
        """
        from app.services.metrics.service import MetricsService
        from app.services.notification.service import NotificationService

        task = FailedTask(
            task_name=task_name,
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            error=error,
            exception_type=exception_type,
            max_retry=max_retry,
            status=STATUS_PENDING,
        )
        created = await self._repo.create(task)

        logger.info(
            "[TaskQueue] Recorded failure: id={}, task='{}', error='{}'",
            created.id, task_name, error,
        )

        # Send notification
        try:
            notifier = NotificationService()
            await notifier.notify(
                notification_type=NotificationService.TASK_FAILED,
                message=f"任务 '{task_name}' 失败，已加入重试队列",
                details={
                    "failed_task_id": created.id,
                    "error": error,
                    "exception_type": exception_type,
                },
            )
        except Exception as e:
            logger.warning("[TaskQueue] Failed to send notification: {}", e)

        return created

    # ── Retry ──────────────────────────────────────────────────

    async def retry_task(
        self,
        task_id: int,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[bool, FailedTask | None]:
        """重试失败任务。

        Args:
            task_id: FailedTask ID
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            (success, task) tuple.
        """
        task = await self._repo.get_by_id(task_id)
        if task is None:
            logger.warning("[TaskQueue] Task {} not found", task_id)
            return False, None

        if not task.can_retry():
            logger.warning(
                "[TaskQueue] Task {} cannot retry (status={}, retry={}/{})",
                task_id, task.status, task.retry_count, task.max_retry,
            )
            return False, task

        # Mark as retrying
        task = await self._repo.mark_retrying(task_id)
        logger.info("[TaskQueue] Retrying task {} (attempt {}/{})", task_id, task.retry_count, task.max_retry)

        try:
            result = await func(*args, **kwargs)

            # Success
            task = await self._repo.mark_resolved(task_id)
            logger.info("[TaskQueue] Task {} resolved after {} retries", task_id, task.retry_count)

            self._update_metrics_on_success()
            return True, task

        except Exception as e:
            # Failed
            error_msg = f"Retry {task.retry_count} failed: {e}"
            if task.retry_count >= task.max_retry:
                task = await self._repo.mark_failed(task_id, error=error_msg)
                logger.error("[TaskQueue] Task {} permanently failed after {} retries", task_id, task.retry_count)
            else:
                task = await self._repo.update_status(task_id, STATUS_PENDING, error=error_msg)
                logger.warning("[TaskQueue] Task {} failed, will retry: {}", task_id, e)

            self._update_metrics_on_failure()
            return False, task

    # ── Query ──────────────────────────────────────────────────

    async def get_failed_tasks(self, status: str | None = None, limit: int = 50) -> list[FailedTask]:
        """获取失败任务列表。"""
        tasks = await self._repo.get_failed(status=status, limit=limit)
        return list(tasks)

    async def get_task(self, task_id: int) -> FailedTask | None:
        """获取单个失败任务。"""
        return await self._repo.get_by_id(task_id)

    # ── Metrics ────────────────────────────────────────────────

    def _update_metrics_on_success(self) -> None:
        """Update metrics when retry succeeds."""
        try:
            from app.services.metrics.service import MetricsService
            # Could add a specific counter for retry success if needed
        except Exception as e:
            logger.warning("[TaskQueue] Failed to update metrics: {}", e)

    def _update_metrics_on_failure(self) -> None:
        """Update metrics when retry fails."""
        try:
            from app.services.metrics.service import MetricsService
            MetricsService.inc_scheduler_task_failed()
        except Exception as e:
            logger.warning("[TaskQueue] Failed to update metrics: {}", e)
