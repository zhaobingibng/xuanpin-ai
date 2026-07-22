"""SchedulerManager -- base scheduling layer wrapping APScheduler's AsyncIOScheduler.

Phase 44.1: pure infrastructure, no business logic.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job
from loguru import logger


class SchedulerManager:
    """Manage APScheduler AsyncIOScheduler lifecycle and job registration.

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

    # -- Lifecycle --------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler. Idempotent."""
        if self._running:
            logger.info("[Scheduler] Already running, skipping start")
            return
        self._scheduler.start()
        self._running = True
        job_count = len(self._scheduler.get_jobs())
        logger.info("[Scheduler] Started -- {} job(s) registered", job_count)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler. Idempotent.

        Args:
            wait: Whether to wait for running jobs (default True).
        """
        if not self._running:
            logger.info("[Scheduler] Already stopped, skipping shutdown")
            return
        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("[Scheduler] Shutdown complete")

    # -- Job management ---------------------------------------------------------

    def add_job(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        trigger: Any = "date",
        job_id: str | None = None,
        name: str | None = None,
        replace_existing: bool = True,
        **trigger_kwargs: Any,
    ) -> Job:
        """Register a scheduled job.

        Args:
            func: Async callable.
            trigger: APScheduler trigger instance or string.
            job_id: Unique job identifier.
            name: Human-readable job name.
            replace_existing: Whether to replace an existing job with the same ID.
            **trigger_kwargs: Passed to the trigger.

        Returns:
            The created APScheduler Job object.
        """
        if not job_id:
            job_id = name or getattr(func, "__name__", "unnamed_job")

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
        """Remove a job by ID. Return True if removed."""
        try:
            self._scheduler.remove_job(job_id)
            logger.info("[Scheduler] Job removed: id={}", job_id)
            return True
        except Exception:
            logger.warning("[Scheduler] Job not found: id={}", job_id)
            return False

    def get_job(self, job_id: str) -> Job | None:
        """Get job details by ID."""
        try:
            return self._scheduler.get_job(job_id)
        except Exception:
            return None

    def get_jobs(self) -> list[dict[str, Any]]:
        """List all registered jobs as summaries."""
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

    # -- Properties -------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def job_count(self) -> int:
        return len(self._scheduler.get_jobs())

    # -- Internal helpers -------------------------------------------------------

    @staticmethod
    def _describe_trigger(job: Job) -> str:
        trigger = job.trigger
        return str(trigger) if trigger is not None else "none"
