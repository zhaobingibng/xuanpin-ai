"""Daily selection task — v2 uses DailySelectionPipeline (Phase 37.2).

Scheduler entry point + manual trigger for the automated product selection
pipeline: candidate products → supplier matching → opportunity scoring →
daily selection report.

Layers:
    APScheduler → daily_selection_job() → tracked_execute
        → _run_pipeline_impl() → DailySelectionPipeline.run()

Tracking:
    - Outer layer: tracked_execute → TaskExecution (RUNNING → SUCCESS/FAILED)
    - Inner layer: DailySelectionPipeline.run(track=False) skips own tracking
      to avoid double-recording.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


# ── Internal pipeline runner ──────────────────────────────────


async def _run_pipeline_impl(
    limit: int = 20,
    top_k: int = 3,
    candidate_limit: int = 1000,
) -> dict[str, Any]:
    """Core implementation — creates its own DB session and runs the pipeline.

    Args:
        limit: TOP-N products in the daily report.
        top_k: supplier matches per product.
        candidate_limit: max candidate products to fetch.

    Returns:
        Pipeline result dict: {"status": "success"|"error", "report": ..., "stats": ...}
    """
    from app.database.base import get_async_session_factory
    from app.services.selection.daily_selection_pipeline import DailySelectionPipeline

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        pipeline = DailySelectionPipeline()
        # track=False — outer tracked_execute already handles TaskExecution.
        result = await pipeline.run(
            session,
            limit=limit,
            top_k=top_k,
            candidate_limit=candidate_limit,
            track=False,
        )
        return result


# ── Scheduler entry point ────────────────────────────────────


async def daily_selection_job() -> None:
    """APScheduler job entry point for daily selection task.

    Called by APScheduler via TaskScheduler.add_daily_selection().
    Uses tracked_execute to record TaskExecution (RUNNING → SUCCESS/FAILED).
    APScheduler gracefully catches any exception raised here.
    """
    from app.tasks.scheduler import TaskScheduler

    logger.info("[daily_selection_job] 定时任务触发")

    try:
        await TaskScheduler.tracked_execute(
            "daily_selection",
            _run_pipeline_impl,
            timeout=600,  # 10 minutes
        )
    except Exception:
        # tracked_execute raises after recording FAILED — APScheduler
        # catches and logs the exception; the job won't crash the scheduler.
        logger.exception("[daily_selection_job] 任务执行异常（已记录至 TaskExecution）")

    logger.info("[daily_selection_job] 定时任务完成")


# ── Manual trigger (for testing / ad-hoc runs) ───────────────


async def run_daily_selection_once(
    limit: int = 20,
    top_k: int = 3,
    candidate_limit: int = 1000,
) -> dict[str, Any]:
    """Manually trigger one pipeline run (no tracked_execute wrapper).

    Useful for testing, debugging, and ad-hoc runs from CLI.

    Args:
        limit: TOP-N products in report.
        top_k: matches per product.
        candidate_limit: max candidate products.

    Returns:
        Pipeline result dict directly (NOT wrapped in tracked_execute).
        Caller can inspect ``result["status"]``, ``result["report"]``, etc.
    """
    logger.info("[run_daily_selection_once] 手动触发选品流水线")
    return await _run_pipeline_impl(
        limit=limit, top_k=top_k, candidate_limit=candidate_limit,
    )
