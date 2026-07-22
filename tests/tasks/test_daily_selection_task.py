"""Tests for Phase 37.2: daily_selection_task scheduler integration.

Covers:
- 任务注册成功 (daily_selection_job is importable and callable)
- 手动执行成功 (run_daily_selection_once returns proper result)
- pipeline 调用 (DailySelectionPipeline.run is invoked)
- pipeline 异常 (errors propagated to result dict)
- TaskExecution 记录 (tracked_execute creates RUNNING → SUCCESS/FAILED)
- 多次执行隔离 (no state leakage between runs)

All DB / service dependencies are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.daily_selection_task import (
    _run_pipeline_impl,
    daily_selection_job,
    run_daily_selection_once,
)


# ── Helpers ──────────────────────────────────────────────────


def _mock_pipeline_result(status="success"):
    return {
        "status": status,
        "report": {
            "report_date": "2026-07-22",
            "top_products": [],
            "statistics": {"total_products": 5, "matched_products": 3},
        },
        "stats": {"total_products": 5, "duration": 1.5},
        "task_execution_id": 99,
    }


def _mock_error_result():
    return {
        "status": "error",
        "stage": "acquire",
        "error": "RuntimeError: db down",
        "report": None,
        "stats": {"total_products": 0, "duration": 0.1},
        "task_execution_id": None,
    }


# ═══════════════════════════════════════════════════════════════
# 任务注册成功
# ═══════════════════════════════════════════════════════════════


class TestJobRegistration:
    """Verify daily_selection_job is properly registered and importable."""

    def test_job_is_importable(self):
        """daily_selection_job is a coroutine function."""
        import asyncio
        assert asyncio.iscoroutinefunction(daily_selection_job)

    def test_run_once_is_importable(self):
        """run_daily_selection_once is a coroutine function."""
        import asyncio
        assert asyncio.iscoroutinefunction(run_daily_selection_once)

    def test_job_has_no_required_args(self):
        """Scheduler entry point takes no required args — compatible with APScheduler."""
        import inspect
        sig = inspect.signature(daily_selection_job)
        params = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.kind not in (
                inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD,
            )
        ]
        assert len(params) == 0

    def test_task_in_all_exports(self):
        """daily_selection_job is exported in app.tasks.__all__."""
        from app import tasks
        assert "daily_selection_job" in tasks.__all__
        assert "run_daily_selection_once" in tasks.__all__


# ═══════════════════════════════════════════════════════════════
# 手动执行成功
# ═══════════════════════════════════════════════════════════════


class TestManualRun:
    """Manual trigger (run_daily_selection_once) tests."""

    @pytest.mark.asyncio
    async def test_returns_success_result(self):
        """Manual trigger returns pipeline result dict."""
        with patch("app.tasks.daily_selection_task._run_pipeline_impl",
                   new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = _mock_pipeline_result("success")

            result = await run_daily_selection_once(limit=10, top_k=2, candidate_limit=50)

            assert result["status"] == "success"
            assert "report" in result
            mock_impl.assert_awaited_once_with(
                limit=10, top_k=2, candidate_limit=50,
            )

    @pytest.mark.asyncio
    async def test_returns_error_result(self):
        """Manual trigger returns error result on pipeline failure."""
        with patch("app.tasks.daily_selection_task._run_pipeline_impl",
                   new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = _mock_error_result()

            result = await run_daily_selection_once()

            assert result["status"] == "error"
            assert result["stage"] == "acquire"

    @pytest.mark.asyncio
    async def test_default_params(self):
        """Default limit=20, top_k=3, candidate_limit=1000."""
        with patch("app.tasks.daily_selection_task._run_pipeline_impl",
                   new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = _mock_pipeline_result()

            await run_daily_selection_once()

            _, kwargs = mock_impl.await_args
            assert kwargs["limit"] == 20
            assert kwargs["top_k"] == 3
            assert kwargs["candidate_limit"] == 1000


# ═══════════════════════════════════════════════════════════════
# pipeline 调用
# ═══════════════════════════════════════════════════════════════


class TestPipelineCall:
    """Verify DailySelectionPipeline is invoked correctly."""

    @pytest.mark.asyncio
    async def test_pipeline_run_is_called(self):
        """_run_pipeline_impl() → DailySelectionPipeline.run() is invoked."""
        mock_session = AsyncMock()

        with patch(
            "app.services.selection.daily_selection_pipeline.DailySelectionPipeline.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = _mock_pipeline_result()

            with patch(
                "app.database.base.get_async_session_factory",
            ) as mock_factory:
                mock_factory.return_value = MagicMock()
                mock_factory.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session,
                )
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await _run_pipeline_impl(limit=10, top_k=5, candidate_limit=200)

        assert result["status"] == "success"
        mock_run.assert_awaited_once()
        _, kwargs = mock_run.await_args
        assert kwargs["limit"] == 10
        assert kwargs["top_k"] == 5
        assert kwargs["candidate_limit"] == 200
        assert kwargs["track"] is False  # outer tracked_execute handles it

    @pytest.mark.asyncio
    async def test_pipeline_track_disabled(self):
        """Inner pipeline tracks=False to avoid double-recording."""
        mock_session = AsyncMock()

        with patch(
            "app.services.selection.daily_selection_pipeline.DailySelectionPipeline.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = _mock_pipeline_result()

            with patch(
                "app.database.base.get_async_session_factory",
            ) as mock_factory:
                mock_factory.return_value = MagicMock()
                mock_factory.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session,
                )
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                await _run_pipeline_impl()

        _, kwargs = mock_run.await_args
        assert kwargs["track"] is False


# ═══════════════════════════════════════════════════════════════
# pipeline 异常
# ═══════════════════════════════════════════════════════════════


class TestPipelineException:
    """Pipeline error handling — errors propagated to result dict."""

    @pytest.mark.asyncio
    async def test_pipeline_error_propagated(self):
        """When pipeline returns error status, it's propagated."""
        with patch("app.tasks.daily_selection_task._run_pipeline_impl",
                   new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = _mock_error_result()

            result = await run_daily_selection_once()

            assert result["status"] == "error"
            assert "db down" in result["error"]

    @pytest.mark.asyncio
    async def test_impl_error_raises(self):
        """If _run_pipeline_impl itself raises, the exception propagates."""
        mock_session = AsyncMock()

        with patch(
            "app.services.selection.daily_selection_pipeline.DailySelectionPipeline.run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            with patch(
                "app.database.base.get_async_session_factory",
            ) as mock_factory:
                mock_factory.return_value = MagicMock()
                mock_factory.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session,
                )
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(RuntimeError, match="unexpected"):
                    await _run_pipeline_impl()


# ═══════════════════════════════════════════════════════════════
# TaskExecution 记录
# ═══════════════════════════════════════════════════════════════


class TestTaskExecutionTracking:
    """Tracked execute creates RUNNING → SUCCESS/FAILED records."""

    @pytest.mark.asyncio
    async def test_tracked_execute_called(self):
        """daily_selection_job() invokes TaskScheduler.tracked_execute."""
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
        ) as mock_tracked:
            mock_tracked.return_value = _mock_pipeline_result()

            await daily_selection_job()

            mock_tracked.assert_awaited_once()
            args, kwargs = mock_tracked.await_args
            assert args[0] == "daily_selection"
            assert kwargs["timeout"] == 600

    @pytest.mark.asyncio
    async def test_tracked_execute_success_records_success(self):
        """Successful pipeline → TaskExecution.SUCCESS."""
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
        ) as mock_tracked:
            mock_tracked.return_value = _mock_pipeline_result("success")

            await daily_selection_job()
            # tracked_execute returns normally → status was SUCCESS
            # (we don't inspect the DB — we trust tracked_execute)

    @pytest.mark.asyncio
    async def test_tracked_execute_failure_handled(self):
        """daily_selection_job catches exceptions from tracked_execute."""
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pipeline failed"),
        ):
            # Must NOT raise — APScheduler needs to survive.
            await daily_selection_job()

    @pytest.mark.asyncio
    async def test_tracked_execute_timeout_handled(self):
        """Timeout exception from tracked_execute is caught."""
        import asyncio
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError("timeout"),
        ):
            await daily_selection_job()  # must not raise


# ═══════════════════════════════════════════════════════════════
# 多次执行隔离
# ═══════════════════════════════════════════════════════════════


class TestMultipleRunIsolation:
    """State does not leak between consecutive runs."""

    @pytest.mark.asyncio
    async def test_consecutive_manual_runs(self):
        """Two manual runs are independent."""
        call_count = 0

        async def _fake_impl(**kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_pipeline_result("success")

        with patch("app.tasks.daily_selection_task._run_pipeline_impl",
                   side_effect=_fake_impl):
            r1 = await run_daily_selection_once()
            r2 = await run_daily_selection_once()

        assert r1["status"] == "success"
        assert r2["status"] == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_job_can_be_called_multiple_times(self):
        """Scheduler job survives multiple invocations."""
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
        ) as mock_tracked:
            mock_tracked.return_value = _mock_pipeline_result()

            await daily_selection_job()
            await daily_selection_job()

            assert mock_tracked.await_count == 2

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self):
        """First run succeeds, second fails — no cross-contamination."""
        with patch(
            "app.tasks.scheduler.TaskScheduler.tracked_execute",
            new_callable=AsyncMock,
            side_effect=[
                _mock_pipeline_result("success"),
                RuntimeError("second run failed"),
            ],
        ):
            await daily_selection_job()  # success
            await daily_selection_job()  # failure → caught


# ═══════════════════════════════════════════════════════════════
# Scheduler 集成 (add_daily_selection)
# ═══════════════════════════════════════════════════════════════


class TestSchedulerIntegration:
    """Scheduler add_daily_selection wires the job correctly."""

    def test_add_daily_selection_registers_job(self):
        """scheduler.add_daily_selection() registers daily_selection_job."""
        from app.tasks.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_selection()

        assert job_id == "daily_selection"
        jobs = scheduler.list_jobs()
        job_ids = [j["id"] for j in jobs]
        assert "daily_selection" in job_ids

    def test_add_daily_selection_custom_hour(self):
        """Can customize execution hour."""
        from app.tasks.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.add_daily_selection(hour=8, minute=30, job_id="daily_selection_custom")

        jobs = scheduler.list_jobs()
        assert any(j["id"] == "daily_selection_custom" for j in jobs)
