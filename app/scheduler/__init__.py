"""Scheduler module — unified task scheduling infrastructure (Phase 44.1).

Provides SchedulerManager as the base scheduling layer using APScheduler's
AsyncIOScheduler. This module is business-logic-free — concrete jobs live
in app/tasks/ or are registered externally.

Usage::

    from app.scheduler import SchedulerManager

    mgr = SchedulerManager()
    mgr.add_job(my_async_func, trigger=CronTrigger(hour=8), job_id="daily_thing")
    mgr.start()
    # ... on shutdown ...
    mgr.shutdown()
"""

from app.scheduler.scheduler import SchedulerManager
from app.scheduler.jobs import list_registered_jobs

__all__ = ["SchedulerManager", "list_registered_jobs"]
