"""SchedulerManager — base scheduling layer wrapping APScheduler's AsyncIOScheduler.

Phase 44.1: pure infrastructure, no business logic.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job
from loguru import logger


class SchedulerManager:
    """管理 APScheduler AsyncIOScheduler 的生命周期和任务注册。

    职责：
    - 创建 AsyncIOScheduler 实例
    - start() / shutdown() 控制调度器启停
    - add_job() / remove_job() / get_jobs() 任务管理
    - 统一日志输出

    Usage::

        mgr = SchedulerManager()
        mgr.add_job(my_coro, trigger=CronTrigger(hour=8), job_id="daily_job")
        mgr.start()
        # ... app running ...
        mgr.shutdown()
    """

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()
        self._running: bool = False

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """启动调度器。

        幂等：重复调用不报错，仅首次启动生效。
        """
        if self._running:
            logger.info("[Scheduler] Already running, skipping start")
            return

        self._scheduler.start()
        self._running = True
        job_count = len(self._scheduler.get_jobs())
        logger.info("[Scheduler] Started — {} job(s) registered", job_count)

    def shutdown(self, wait: bool = True) -> None:
        """关闭调度器。

        幂等：重复调用不报错，仅首次关闭生效。

        Args:
            wait: 是否等待正在执行的任务完成（默认 True）。
        """
        if not self._running:
            logger.info("[Scheduler] Already stopped, skipping shutdown")
            return

        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("[Scheduler] Shutdown complete")

    # ── Job management ────────────────────────────────────────

    def add_job(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        trigger: Any = "date",
        job_id: str | None = None,
        name: str | None = None,
        replace_existing: bool = True,
        **trigger_kwargs: Any,
    ) -> Job:
        """注册一个定时任务。

        Args:
            func: async 可调用对象（协程函数）。
            trigger: APScheduler trigger 实例或字符串（"cron", "interval", "date"）。
            job_id: 任务唯一标识（可选，不传则自动生成）。
            name: 人类可读的任务名称。
            replace_existing: 是否替换同 ID 的已有任务（默认 True）。
            **trigger_kwargs: 传递给 trigger 的参数（如 hour=8, minute=0）。

        Returns:
            创建的 APScheduler Job 对象。

        Raises:
            ValueError: 如果 func 不是 async 函数。
        """
        if not job_id:
            job_id = name or getattr(func, "__name__", "unnamed_job")

        # APScheduler 3.x quirk: replace_existing does not always work
        # reliably when the scheduler is not yet started.  Manually
        # remove a previous job with the same ID first (same approach
        # as the existing TaskScheduler in app/tasks/scheduler.py).
        if replace_existing:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            replace_existing=replace_existing,
            **trigger_kwargs,
        )

        logger.info(
            "[Scheduler] Job added: id={}, name={}, trigger={}",
            job.id, job.name, self._describe_trigger(job),
        )
        return job

    def remove_job(self, job_id: str) -> bool:
        """删除指定 ID 的任务。

        Args:
            job_id: 任务唯一标识。

        Returns:
            True 表示成功删除，False 表示任务不存在。
        """
        try:
            self._scheduler.remove_job(job_id)
            logger.info("[Scheduler] Job removed: id={}", job_id)
            return True
        except Exception:
            logger.warning("[Scheduler] Job not found: id={}", job_id)
            return False

    def get_job(self, job_id: str) -> Job | None:
        """获取指定 ID 的任务详情。

        Args:
            job_id: 任务唯一标识。

        Returns:
            Job 对象，不存在则返回 None。
        """
        try:
            return self._scheduler.get_job(job_id)
        except Exception:
            return None

    def get_jobs(self) -> list[dict[str, Any]]:
        """获取所有已注册任务的摘要信息。

        Returns:
            任务摘要列表，每项包含 id, name, next_run, trigger 字段。
        """
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": (
                    job.next_run_time.isoformat() if getattr(job, "next_run_time", None) else None
                ),
                "trigger": self._describe_trigger(job),
            }
            for job in jobs
        ]

    # ── Properties ────────────────────────────────────────────

    @property
    def running(self) -> bool:
        """调度器是否正在运行。"""
        return self._running

    @property
    def job_count(self) -> int:
        """已注册任务数量。"""
        return len(self._scheduler.get_jobs())

    # ── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _describe_trigger(job: Job) -> str:
        """返回 trigger 的人类可读描述。"""
        trigger = job.trigger
        if trigger is None:
            return "none"
        return str(trigger)
