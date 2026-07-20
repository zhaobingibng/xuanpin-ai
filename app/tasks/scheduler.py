"""Task scheduler — APScheduler wrapper for scheduled product analysis."""

from __future__ import annotations

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tasks.jobs import auto_crawl_job, daily_crawl_job, daily_pipeline_job


class TaskScheduler:
    """Manage scheduled tasks using APScheduler.

    Usage::

        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(
            keywords=["防晒霜", "蓝牙耳机"],
            platforms=["xiaohongshu", "douyin"],
            hour=9, minute=0,
        )
        scheduler.start()
        # ... later ...
        scheduler.stop()
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._running = False

    # ── Job management ────────────────────────────────────────

    def add_daily_crawl(
        self,
        keywords: list[str],
        platforms: list[str] | None = None,
        max_pages: int = 3,
        save_to_db: bool = True,
        hour: int = 2,
        minute: int = 0,
        job_id: str = "daily_crawl",
    ) -> str:
        """Schedule a daily crawl job.

        Args:
            keywords: search keywords
            platforms: platforms to crawl (None = all)
            max_pages: max pages per keyword per platform
            save_to_db: whether to persist to database
            hour: hour to run (24h format, default 02:00)
            minute: minute to run
            job_id: unique job identifier

        Returns:
            The job ID.
        """
        trigger = CronTrigger(hour=hour, minute=minute)

        # Manually remove existing job first — replace_existing only works
        # reliably when the scheduler is running (APScheduler 3.x quirk).
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            daily_crawl_job,
            trigger=trigger,
            kwargs={
                "keywords": keywords,
                "platforms": platforms,
                "max_pages": max_pages,
                "save_to_db": save_to_db,
            },
            id=job_id,
            name=f"Daily crawl ({', '.join(keywords)})",
            replace_existing=True,
        )

        logger.info(
            "Scheduled job '{}': daily at {:02d}:{:02d}, keywords={}",
            job_id, hour, minute, keywords,
        )
        return job_id

    def add_auto_crawl(
        self,
        hour: int = 2,
        minute: int = 0,
        job_id: str = "daily_crawl",
    ) -> str:
        """Schedule auto_crawl_job — reads keywords/platforms from settings.

        Args:
            hour: hour to run (24h format, default 02:00)
            minute: minute to run
            job_id: unique job identifier

        Returns:
            The job ID.
        """
        trigger = CronTrigger(hour=hour, minute=minute)

        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            auto_crawl_job,
            trigger=trigger,
            id=job_id,
            name="Auto crawl (from settings)",
            replace_existing=True,
        )

        logger.info(
            "Scheduled job '{}': daily at {:02d}:{:02d} (auto from settings)",
            job_id, hour, minute,
        )
        return job_id

    def add_daily_pipeline(
        self,
        keywords: list[str] | None = None,
        platforms: list[str] | None = None,
        max_pages: int = 3,
        hour: int = 8,
        minute: int = 0,
        job_id: str = "daily_pipeline",
    ) -> str:
        """Schedule the daily pipeline job.

        Args:
            keywords: search keywords (None = default list)
            platforms: platforms to crawl (None = all)
            max_pages: max pages per keyword per platform
            hour: hour to run (24h format, default 08:00)
            minute: minute to run
            job_id: unique job identifier

        Returns:
            The job ID.
        """
        trigger = CronTrigger(hour=hour, minute=minute)

        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            daily_pipeline_job,
            trigger=trigger,
            kwargs={
                "keywords": keywords,
                "platforms": platforms,
                "max_pages": max_pages,
            },
            id=job_id,
            name="Daily pipeline (crawl → clean → save → trend → ranking)",
            replace_existing=True,
        )

        logger.info(
            "Scheduled job '{}': daily at {:02d}:{:02d}",
            job_id, hour, minute,
        )
        return job_id

    def add_job(
        self,
        func,
        trigger: str | CronTrigger = "cron",
        job_id: str | None = None,
        name: str | None = None,
        **trigger_kwargs,
    ) -> str:
        """Add a generic scheduled job.

        Args:
            func: async function to call
            trigger: trigger type or CronTrigger instance
            job_id: unique identifier
            name: human-readable name
            **trigger_kwargs: passed to the trigger (hour, minute, etc.)

        Returns:
            The job ID.
        """
        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True,
            **trigger_kwargs,
        )
        logger.info("Scheduled job '{}': {}", job.id, name or func.__name__)
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job by ID. Return True if removed."""
        try:
            self._scheduler.remove_job(job_id)
            logger.info("Removed job: {}", job_id)
            return True
        except Exception:
            logger.warning("Job not found: {}", job_id)
            return False

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs with their info."""
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(getattr(job, "next_run_time", None)) if getattr(job, "next_run_time", None) else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started — {} jobs registered", len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._running:
            self._scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Scheduler stopped")

    @property
    def running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    # ── Task Execution Tracking ────────────────────────────────

    @staticmethod
    async def tracked_execute(
        task_name: str,
        func,
        *args,
        timeout: float | None = None,
        **kwargs,
    ):
        """Execute a job with TaskExecution record tracking.

        Creates a RUNNING record, executes the function,
        then updates to SUCCESS or FAILED with duration.

        Args:
            task_name: Task name for logging.
            func: Async function to execute.
            *args: Positional arguments.
            timeout: Optional timeout in seconds (None = no timeout).
            **kwargs: Keyword arguments.
        """
        import asyncio
        from datetime import datetime

        from app.services.metrics.service import MetricsService

        start_time = datetime.now()
        record_id = None

        # Increment task counter
        MetricsService.inc_scheduler_task()

        # Create RUNNING record
        try:
            from app.database.base import get_async_session_factory
            from app.database.task_execution_repository import TaskExecutionRepository
            from app.models.task_execution import TaskExecution

            session_factory = get_async_session_factory()
            async with session_factory() as session:
                repo = TaskExecutionRepository(session)
                record = TaskExecution(task_name=task_name, status="RUNNING")
                created = await repo.create(record)
                await session.commit()
                record_id = created.id
        except Exception as e:
            logger.warning("[Scheduler] Failed to record task start: {}", e)

        # Execute (with optional timeout)
        error_msg = None
        status = "SUCCESS"
        try:
            if timeout is not None:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            else:
                result = await func(*args, **kwargs)
            return result
        except asyncio.TimeoutError:
            status = "FAILED"
            error_msg = f"TaskTimeoutError: exceeded {timeout}s limit"
            MetricsService.inc_scheduler_task_failed()
            logger.error("[Scheduler] Task '{}' timed out after {}s", task_name, timeout)
            raise
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            MetricsService.inc_scheduler_task_failed()
            logger.error("[Scheduler] Task '{}' failed: {}", task_name, e)
            raise
        finally:
            duration = (datetime.now() - start_time).total_seconds()
            if record_id is not None:
                try:
                    async with session_factory() as session:
                        repo = TaskExecutionRepository(session)
                        await repo.finish(
                            record_id,
                            status=status,
                            duration=duration,
                            error=error_msg,
                        )
                        await session.commit()
                except Exception as e:
                    logger.warning("[Scheduler] Failed to record task finish: {}", e)
