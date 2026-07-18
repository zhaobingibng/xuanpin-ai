"""Task scheduler — APScheduler wrapper for scheduled product analysis."""

from __future__ import annotations

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tasks.jobs import daily_crawl_job


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
        hour: int = 9,
        minute: int = 0,
        job_id: str = "daily_crawl",
    ) -> str:
        """Schedule a daily crawl job.

        Args:
            keywords: search keywords
            platforms: platforms to crawl (None = all)
            max_pages: max pages per keyword per platform
            save_to_db: whether to persist to database
            hour: hour to run (24h format, default 09:00)
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
