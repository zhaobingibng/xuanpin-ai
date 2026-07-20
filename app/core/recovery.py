"""Global exception recovery — unified error handling with auto-retry."""

from __future__ import annotations

import asyncio
import traceback
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger

T = TypeVar("T")


# ── Exception Categories ────────────────────────────────────────

class CrawlerException(Exception):
    """Crawler-specific errors (network, page, login)."""
    pass


class DatabaseException(Exception):
    """Database connection or query errors."""
    pass


class SchedulerException(Exception):
    """Task scheduling errors."""
    pass


class APIException(Exception):
    """API layer errors."""
    pass


# ── Recovery Manager ────────────────────────────────────────────


class RecoveryManager:
    """统一异常捕获和自动恢复。

    Supports:
    - Crawler exceptions (network, timeout, page crash)
    - Database exceptions (connection, query)
    - API exceptions (request, serialization)
    - Scheduler exceptions (job registration, execution)

    On failure:
    - Logs error with full traceback
    - Auto-retries up to max_retries
    - Records failure for monitoring
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 5.0) -> None:
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._failures: list[dict] = []

    @property
    def failures(self) -> list[dict]:
        """Return recorded failures."""
        return list(self._failures)

    @property
    def failure_count(self) -> int:
        return len(self._failures)

    def clear_failures(self) -> None:
        """Clear recorded failures."""
        self._failures.clear()

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        category: str = "unknown",
        task_name: str = "",
        **kwargs: Any,
    ) -> T | None:
        """Execute an async function with recovery.

        Args:
            func: async function to execute.
            *args: positional arguments.
            category: exception category (crawler/database/api/scheduler).
            task_name: task name for logging.
            **kwargs: keyword arguments.

        Returns:
            Function result, or None if all retries exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                tb = traceback.format_exc()
                logger.error(
                    "[Recovery] {}/{} attempt {}/{} failed: {}\n{}",
                    category,
                    task_name,
                    attempt,
                    self._max_retries,
                    e,
                    tb,
                )

                self._failures.append({
                    "category": category,
                    "task_name": task_name,
                    "attempt": attempt,
                    "error": str(e),
                })

                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay)

        logger.error(
            "[Recovery] {}/{} all {} retries exhausted",
            category, task_name, self._max_retries,
        )

        # Update metrics for exhausted retries
        try:
            from app.services.metrics.service import MetricsService
            if category == "crawler":
                MetricsService.inc_crawl_failed()
            elif category == "scheduler":
                MetricsService.inc_scheduler_task_failed()
        except Exception:
            pass  # Metrics failure should not affect recovery

        # Record to FailedTask queue for retry management
        try:
            from app.database.base import get_async_session_factory
            from app.services.task_queue.service import TaskQueueService

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                queue_svc = TaskQueueService(session)
                await queue_svc.record_failure(
                    task_name=task_name or category,
                    error=str(last_error),
                    exception_type=type(last_error).__name__ if last_error else None,
                    max_retry=self._max_retries,
                )
        except Exception:
            pass  # Queue failure should not affect recovery

        return None
