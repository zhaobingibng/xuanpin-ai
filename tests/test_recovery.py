"""Tests for Phase 9.7.6 — RecoveryManager.

Covers: execute with retry, failure recording, category handling.
"""

from unittest.mock import AsyncMock

import pytest

from app.core.recovery import (
    RecoveryManager,
    CrawlerException,
    DatabaseException,
    SchedulerException,
    APIException,
)


# ── TestRecoveryManager ────────────────────────────────────────


class TestRecoveryManager:
    """RecoveryManager.execute() with retry and failure recording."""

    @pytest.mark.anyio
    async def test_execute_success(self):
        rm = RecoveryManager(max_retries=3, retry_delay=0)
        func = AsyncMock(return_value="ok")

        result = await rm.execute(func, category="test", task_name="t1")
        assert result == "ok"
        func.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_retry_then_success(self):
        rm = RecoveryManager(max_retries=3, retry_delay=0)
        func = AsyncMock(side_effect=[RuntimeError("fail"), "ok"])

        result = await rm.execute(func, category="test", task_name="t1")
        assert result == "ok"
        assert func.call_count == 2

    @pytest.mark.anyio
    async def test_execute_all_retries_exhausted(self):
        rm = RecoveryManager(max_retries=2, retry_delay=0)
        func = AsyncMock(side_effect=RuntimeError("permanent"))

        result = await rm.execute(func, category="crawler", task_name="t1")
        assert result is None
        assert func.call_count == 2

    @pytest.mark.anyio
    async def test_failures_recorded(self):
        rm = RecoveryManager(max_retries=2, retry_delay=0)
        func = AsyncMock(side_effect=RuntimeError("db error"))

        await rm.execute(func, category="database", task_name="db_task")

        assert rm.failure_count == 2
        assert rm.failures[0]["category"] == "database"
        assert rm.failures[0]["task_name"] == "db_task"
        assert rm.failures[0]["error"] == "db error"

    @pytest.mark.anyio
    async def test_clear_failures(self):
        rm = RecoveryManager(max_retries=1, retry_delay=0)
        func = AsyncMock(side_effect=RuntimeError("err"))

        await rm.execute(func, category="test", task_name="t1")
        assert rm.failure_count == 1

        rm.clear_failures()
        assert rm.failure_count == 0

    @pytest.mark.anyio
    async def test_passes_args_and_kwargs(self):
        rm = RecoveryManager(max_retries=1, retry_delay=0)
        func = AsyncMock(return_value="result")

        result = await rm.execute(func, "arg1", "arg2", category="test", key="val")
        assert result == "result"
        func.assert_called_once_with("arg1", "arg2", key="val")

    @pytest.mark.anyio
    async def test_retry_delay_zero(self):
        """retry_delay=0 should not add real sleep time."""
        rm = RecoveryManager(max_retries=3, retry_delay=0)
        func = AsyncMock(side_effect=[RuntimeError("a"), RuntimeError("b"), "ok"])

        result = await rm.execute(func, category="test", task_name="t1")
        assert result == "ok"
        assert func.call_count == 3


# ── TestExceptionCategories ────────────────────────────────────


class TestExceptionCategories:
    """Exception category classes exist and are Exception subclasses."""

    def test_crawler_exception(self):
        assert issubclass(CrawlerException, Exception)

    def test_database_exception(self):
        assert issubclass(DatabaseException, Exception)

    def test_scheduler_exception(self):
        assert issubclass(SchedulerException, Exception)

    def test_api_exception(self):
        assert issubclass(APIException, Exception)

    def test_crawler_exception_message(self):
        e = CrawlerException("page crashed")
        assert str(e) == "page crashed"
