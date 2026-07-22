"""TaskExecutionLogger — task execution recording infrastructure (Phase 44.3.0).

Wraps any async function with automatic TaskExecution recording:
    RUNNING → SUCCESS  (on normal return)
    RUNNING → FAILED   (on exception)

Design principles:
- Scheduler-agnostic: works with SchedulerManager, standalone, or via TaskRegistry.
- Pure infrastructure: no business logic (no crawl, match, report awareness).
- Thin wrapper over existing TaskExecution model + TaskExecutionRepository.
- No modification to existing TaskScheduler.tracked_execute.

Usage::

    from app.tasks.execution_logger import TaskExecutionLogger

    logger = TaskExecutionLogger()
    result = await logger.execute("my_task", my_async_func, arg1, kw=val)

    # Query history
    recent = await logger.get_recent_executions(limit=20)
    by_task = await logger.get_executions_by_task("my_task", limit=10)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, TypeVar

from loguru import logger as loguru_logger

T = TypeVar("T")


class TaskExecutionLogger:
    """任务执行日志记录器。

    包装 async 函数调用，自动在数据库记录 TaskExecution：
    - 调用前：插入 RUNNING 记录
    - 成功返回：更新为 SUCCESS + 记录耗时
    - 异常退出：更新为 FAILED + 记录错误信息

    数据库会话由 session_factory 管理（每次 execute 独立会话），
    确保单个任务的数据库失败不影响调度器或其他任务。

    Usage::

        logger = TaskExecutionLogger()
        result = await logger.execute("daily_report", gen_report, arg1)

        # 查询历史
        for record in await logger.get_recent_executions(5):
            print(record.task_name, record.status, record.duration)
    """

    def __init__(self) -> None:
        pass

    # ── Core: execute with tracking ───────────────────────────

    async def execute(
        self,
        task_name: str,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        """执行 func 并自动记录 TaskExecution。

        Args:
            task_name: 任务名称（用于日志和数据库记录）。
            func: async 协程函数。
            *args: 传递给 func 的位置参数。
            timeout: 可选超时（秒）。超时后记录 FAILED + TimeoutError。
            **kwargs: 传递给 func 的关键字参数。

        Returns:
            func 的返回值（成功时）。

        Raises:
            原样抛出 func 的异常（已记录 FAILED 后）。
        """
        from app.database.base import get_async_session_factory
        from app.database.task_execution_repository import TaskExecutionRepository
        from app.models.task_execution import TaskExecution

        start_time = datetime.now(timezone.utc)
        record_id: int | None = None

        # ── 1. 记录 RUNNING ───────────────────────────────────
        try:
            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = TaskExecutionRepository(session)
                record = TaskExecution(task_name=task_name, status="RUNNING")
                created = await repo.create(record)
                await session.commit()
                record_id = created.id
                loguru_logger.debug(
                    "[TaskExecution] {} #{} — RUNNING", task_name, record_id,
                )

        except Exception as e:
            # 记录 RUNNING 失败不影响任务执行
            loguru_logger.warning(
                "[TaskExecution] Failed to record RUNNING for '{}': {}", task_name, e,
            )

        # ── 2. 执行业务函数 ───────────────────────────────────
        status: str = "SUCCESS"
        error_msg: str | None = None
        result: T

        try:
            if timeout is not None:
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout,
                )
            else:
                result = await func(*args, **kwargs)
            return result

        except asyncio.TimeoutError:
            status = "FAILED"
            error_msg = f"TaskTimeoutError: exceeded {timeout}s limit"
            loguru_logger.error(
                "[TaskExecution] {} #{} — TIMEOUT after {}s",
                task_name, record_id, timeout,
            )
            raise

        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            loguru_logger.error(
                "[TaskExecution] {} #{} — FAILED: {}", task_name, record_id, e,
            )
            raise

        finally:
            # ── 3. 更新最终状态 ───────────────────────────────
            if record_id is not None:
                try:
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                    async with session_factory() as session:
                        repo = TaskExecutionRepository(session)
                        await repo.finish(
                            record_id,
                            status=status,
                            duration=round(duration, 3),
                            error=error_msg,
                        )
                        await session.commit()
                    loguru_logger.debug(
                        "[TaskExecution] {} #{} — {} ({:.2f}s)",
                        task_name, record_id, status, duration,
                    )
                except Exception as e:
                    loguru_logger.warning(
                        "[TaskExecution] Failed to record finish for '{}' #{}: {}",
                        task_name, record_id, e,
                    )

    # ── Query ─────────────────────────────────────────────────

    async def get_recent_executions(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近的执行记录。

        Args:
            limit: 返回条数上限。

        Returns:
            执行记录摘要列表。
        """
        from app.database.base import get_async_session_factory
        from app.database.task_execution_repository import TaskExecutionRepository

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            repo = TaskExecutionRepository(session)
            records = await repo.get_recent(limit=limit)
            return [
                {
                    "id": r.id,
                    "task_name": r.task_name,
                    "status": r.status,
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration": r.duration,
                    "error": r.error,
                }
                for r in records
            ]

    async def get_executions_by_task(
        self, task_name: str, limit: int = 10,
    ) -> list[dict[str, Any]]:
        """获取指定任务的执行记录。

        Args:
            task_name: 任务名称。
            limit: 返回条数上限。

        Returns:
            执行记录摘要列表。
        """
        from app.database.base import get_async_session_factory
        from app.database.task_execution_repository import TaskExecutionRepository

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            repo = TaskExecutionRepository(session)
            records = await repo.get_by_task(task_name, limit=limit)
            return [
                {
                    "id": r.id,
                    "task_name": r.task_name,
                    "status": r.status,
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration": r.duration,
                    "error": r.error,
                }
                for r in records
            ]

    async def get_failed_executions(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近的失败执行记录。

        Args:
            limit: 返回条数上限。

        Returns:
            FAILED 状态的执行记录摘要列表。
        """
        all_records = await self.get_recent_executions(limit=limit * 2)
        return [r for r in all_records if r["status"] == "FAILED"][:limit]
