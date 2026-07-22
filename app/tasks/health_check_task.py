"""System health check task — Phase 44.3.1.

Verifies the full closed loop of:
    TaskRegistry → SchedulerManager → TaskExecutionLogger.

Checks:
1. Database connectivity (SELECT 1)
2. Current time
3. Scheduler running state (if accessible)

This is a pure infrastructure task — no business logic (no crawl, match, report).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import text


# ── Core task function ─────────────────────────────────────────


async def system_health_check(scheduler: Any = None) -> dict[str, Any]:
    """Run system health checks and return structured result.

    Args:
        scheduler: Optional SchedulerManager instance to check scheduler state.

    Returns:
        Structured result dict::

            {
                "status": "healthy" | "degraded" | "unhealthy",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "checks": {
                    "database": {"status": "ok"|"error", "detail": str},
                    "time": {"iso": str, "unix": float},
                    "scheduler": {"status": "running"|"stopped"|"unknown", "detail": str},
                }
            }
    """
    from app.database.base import get_async_session_factory

    checks: dict[str, dict[str, Any]] = {}

    # ── 1. Database ────────────────────────────────────────
    try:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "detail": "SELECT 1 succeeded"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}

    # ── 2. Current time ────────────────────────────────────
    now = datetime.now(timezone.utc)
    checks["time"] = {
        "iso": now.isoformat(),
        "unix": time.time(),
    }

    # ── 3. Scheduler state ─────────────────────────────────
    if scheduler is not None:
        try:
            if scheduler.running:
                checks["scheduler"] = {
                    "status": "running",
                    "detail": f"Scheduler running, {scheduler.job_count} job(s)",
                }
            else:
                checks["scheduler"] = {
                    "status": "stopped",
                    "detail": "Scheduler not running",
                }
        except Exception as e:
            checks["scheduler"] = {"status": "error", "detail": str(e)}
    else:
        checks["scheduler"] = {
            "status": "unknown",
            "detail": "No scheduler reference provided",
        }

    # ── Determine overall status ───────────────────────────
    if checks["database"]["status"] != "ok":
        overall = "unhealthy"
    elif checks.get("scheduler", {}).get("status") == "error":
        overall = "degraded"
    else:
        overall = "healthy"

    result = {
        "status": overall,
        "timestamp": now.isoformat(),
        "checks": checks,
    }

    logger.info(
        "[HealthCheck] result: status={}, db={}, scheduler={}",
        overall,
        checks["database"]["status"],
        checks["scheduler"]["status"],
    )
    return result


# ── Registry integration ───────────────────────────────────────


def register_health_check_task(
    registry: Any,
    scheduler_manager: Any = None,
) -> Any:
    """Register system_health_check into a TaskRegistry.

    Wraps the health check with TaskExecutionLogger so every run is recorded
    in the task_executions table.

    Args:
        registry: TaskRegistry instance.
        scheduler_manager: Optional SchedulerManager for scheduler state check.

    Returns:
        The registered TaskDefinition.
    """
    from app.tasks.execution_logger import TaskExecutionLogger

    execution_logger = TaskExecutionLogger()

    async def _health_check_wrapped() -> dict[str, Any]:
        """Wrapped health check with execution logging."""
        return await execution_logger.execute(
            "system_health_check",
            system_health_check,
            scheduler=scheduler_manager,
        )

    return registry.register(
        name="system_health_check",
        func=_health_check_wrapped,
        trigger="cron",
        hour=1,
        minute=0,
    )
