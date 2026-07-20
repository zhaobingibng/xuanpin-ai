"""Task timeout management — automatic timeout detection and cancellation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger

T = TypeVar("T")


# ── Timeout Exception ──────────────────────────────────────────


class TaskTimeoutError(Exception):
    """Raised when a task exceeds its configured timeout."""

    def __init__(self, task_name: str, timeout_seconds: float) -> None:
        self.task_name = task_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Task '{task_name}' timed out after {timeout_seconds}s"
        )


# ── TaskTimeoutManager ─────────────────────────────────────────


class TaskTimeoutManager:
    """任务超时管理器。

    Features:
    - Set task timeout via seconds parameter
    - Async task timeout detection using asyncio.wait_for
    - Automatic task cancellation on timeout
    - Record TaskExecution failure
    - Call NotificationService for notification
    - Update Metrics

    Usage::

        manager = TaskTimeoutManager()
        result = await manager.execute_with_timeout(
            task_name="crawl_job",
            func=some_async_func,
            timeout=300,  # 5 minutes
            arg1="value",
        )
    """

    # Default timeout (seconds)
    DEFAULT_TIMEOUT = 3600  # 1 hour

    def __init__(self, default_timeout: float | None = None) -> None:
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT

    @property
    def default_timeout(self) -> float:
        """Return the default timeout value."""
        return self._default_timeout

    async def execute_with_timeout(
        self,
        task_name: str,
        func: Callable[..., Awaitable[T]],
        timeout: float | None = None,
        *args: Any,
        notify_on_timeout: bool = True,
        record_failure: bool = True,
        **kwargs: Any,
    ) -> T:
        """Execute an async function with timeout protection.

        Args:
            task_name: Task name for logging and notifications.
            func: Async function to execute.
            timeout: Timeout in seconds (None uses default).
            *args: Positional arguments for the function.
            notify_on_timeout: Send notification on timeout.
            record_failure: Record TaskExecution failure on timeout.
            **kwargs: Keyword arguments for the function.

        Returns:
            Function result.

        Raises:
            TaskTimeoutError: If the task exceeds the timeout.
            Exception: Any exception raised by the function.
        """
        timeout = timeout if timeout is not None else self._default_timeout
        start_time = datetime.now()

        logger.info("[Timeout] Starting task '{}' with timeout={}s", task_name, timeout)

        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout,
            )
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info("[Timeout] Task '{}' completed in {:.2f}s", task_name, elapsed)
            return result

        except asyncio.TimeoutError:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(
                "[Timeout] Task '{}' timed out after {:.2f}s (limit={}s)",
                task_name, elapsed, timeout,
            )

            # Update metrics
            self._update_metrics_on_timeout(task_name)

            # Send notification
            if notify_on_timeout:
                await self._notify_timeout(task_name, timeout)

            # Record failure
            if record_failure:
                await self._record_timeout_failure(task_name, timeout)

            raise TaskTimeoutError(task_name, timeout)

    def _update_metrics_on_timeout(self, task_name: str) -> None:
        """Update metrics when a task times out."""
        try:
            from app.services.metrics.service import MetricsService
            MetricsService.inc_scheduler_task_failed()
        except Exception as e:
            logger.warning("[Timeout] Failed to update metrics for '{}': {}", task_name, e)

    async def _notify_timeout(self, task_name: str, timeout: float) -> None:
        """Send notification about task timeout."""
        try:
            from app.services.notification.service import NotificationService
            notifier = NotificationService()
            await notifier.notify(
                notification_type=NotificationService.TASK_FAILED,
                message=f"任务 '{task_name}' 超时 ({timeout}s)",
                details={"task_name": task_name, "timeout_seconds": timeout},
            )
        except Exception as e:
            logger.warning("[Timeout] Failed to send notification for '{}': {}", task_name, e)

    async def _record_timeout_failure(self, task_name: str, timeout: float) -> None:
        """Record task timeout failure in TaskExecution."""
        try:
            from app.database.base import get_async_session_factory
            from app.database.task_execution_repository import TaskExecutionRepository

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = TaskExecutionRepository(session)
                # Find the most recent RUNNING record for this task
                records = await repo.get_by_task(task_name, limit=1)
                if records and records[0].status == "RUNNING":
                    await repo.finish(
                        records[0].id,
                        status="FAILED",
                        duration=timeout,
                        error=f"TaskTimeoutError: exceeded {timeout}s limit",
                    )
        except Exception as e:
            logger.warning("[Timeout] Failed to record failure for '{}': {}", task_name, e)
