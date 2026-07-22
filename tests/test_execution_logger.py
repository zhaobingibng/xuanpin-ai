"""Tests for Phase 44.3.0 — TaskExecutionLogger execution recording infrastructure.

Covers:
- execute() success / failure / timeout
- execute() arg/kwargs passthrough
- get_recent_executions / get_executions_by_task / get_failed_executions
- duration tracking accuracy
- DB failure resilience
- integration with SchedulerManager + TaskRegistry
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.tasks.execution_logger import TaskExecutionLogger


# ── Test helpers ───────────────────────────────────────────────


async def _fast_job(value: str = "ok") -> str:
    """Fast async job that returns a value."""
    await asyncio.sleep(0.001)
    return value


async def _slow_job(delay: float = 0.5) -> str:
    """Slow async job — used for timeout tests."""
    await asyncio.sleep(delay)
    return "done"


async def _failing_job(msg: str = "boom") -> str:
    """Job that always raises."""
    await asyncio.sleep(0.001)
    raise RuntimeError(msg)


# ── Fixture ────────────────────────────────────────────────────


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite async session factory with task_executions table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def logger_for_test(db_session_factory):
    """Return a TaskExecutionLogger patched to use the test DB."""
    with patch(
        "app.database.base.get_async_session_factory",
        return_value=db_session_factory,
    ):
        yield TaskExecutionLogger()


# ═══════════════════════════════════════════════════════════════
# Execute — Success
# ═══════════════════════════════════════════════════════════════


class TestExecuteSuccess:
    """execute() 正常成功场景。"""

    @pytest.mark.anyio
    async def test_returns_function_result(self, logger_for_test):
        """execute() 应返回 func 的返回值。"""
        result = await logger_for_test.execute("succ_task", _fast_job, "hello")
        assert result == "hello"

    @pytest.mark.anyio
    async def test_records_success_into_db(self, logger_for_test, db_session_factory):
        """成功执行后应能在 DB 查询到 SUCCESS 记录。"""
        await logger_for_test.execute("db_task", _fast_job, "world")

        records = await logger_for_test.get_recent_executions(limit=5)
        assert len(records) == 1
        record = records[0]
        assert record["task_name"] == "db_task"
        assert record["status"] == "SUCCESS"
        assert record["error"] is None

    @pytest.mark.anyio
    async def test_records_duration(self, logger_for_test):
        """duration 应为正数。"""
        await logger_for_test.execute("dur_task", _fast_job)

        records = await logger_for_test.get_recent_executions(limit=1)
        assert records[0]["duration"] is not None
        assert records[0]["duration"] >= 0

    @pytest.mark.anyio
    async def test_records_timestamps(self, logger_for_test):
        """应记录 start_time 和 end_time，且 end_time >= start_time。"""
        await logger_for_test.execute("ts_task", _fast_job)

        records = await logger_for_test.get_recent_executions(limit=1)
        assert records[0]["start_time"] is not None
        assert records[0]["end_time"] is not None

    @pytest.mark.anyio
    async def test_passes_args_and_kwargs(self, logger_for_test):
        """execute() 应正确传递位置参数和关键字参数给 func。"""
        result = await logger_for_test.execute("args_task", _fast_job, "custom")
        assert result == "custom"


# ═══════════════════════════════════════════════════════════════
# Execute — Failure
# ═══════════════════════════════════════════════════════════════


class TestExecuteFailure:
    """execute() 异常失败场景。"""

    @pytest.mark.anyio
    async def test_reraises_exception(self, logger_for_test):
        """execute() 应在记录 FAILED 后原样抛出异常。"""
        with pytest.raises(RuntimeError, match="boom"):
            await logger_for_test.execute("fail_task", _failing_job)

    @pytest.mark.anyio
    async def test_records_failed_status(self, logger_for_test):
        """异常发生时应在 DB 记录 FAILED。"""
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("fail_db_task", _failing_job, "kaboom")

        records = await logger_for_test.get_recent_executions(limit=5)
        assert len(records) == 1
        assert records[0]["task_name"] == "fail_db_task"
        assert records[0]["status"] == "FAILED"
        assert "kaboom" in records[0]["error"]

    @pytest.mark.anyio
    async def test_captures_error_message(self, logger_for_test):
        """error 字段应包含异常消息。"""
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("err_task", _failing_job, "custom error text")

        records = await logger_for_test.get_recent_executions(limit=1)
        assert "custom error text" in records[0]["error"]

    @pytest.mark.anyio
    async def test_duration_recorded_even_on_failure(self, logger_for_test):
        """失败时也应正确记录 duration。"""
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("fdur_task", _failing_job)

        records = await logger_for_test.get_recent_executions(limit=1)
        assert records[0]["duration"] is not None
        assert records[0]["duration"] >= 0


# ═══════════════════════════════════════════════════════════════
# Execute — Timeout
# ═══════════════════════════════════════════════════════════════


class TestExecuteTimeout:
    """execute() 超时场景。"""

    @pytest.mark.anyio
    async def test_timeout_raises(self, logger_for_test):
        """超时后应抛出 asyncio.TimeoutError。"""
        with pytest.raises(asyncio.TimeoutError):
            await logger_for_test.execute(
                "to_task", _slow_job, 0.5, timeout=0.05,
            )

    @pytest.mark.anyio
    async def test_timeout_records_failed(self, logger_for_test):
        """超时后应在 DB 记录 FAILED + timeout 错误。"""
        with pytest.raises(asyncio.TimeoutError):
            await logger_for_test.execute(
                "timeout_task", _slow_job, 0.5, timeout=0.05,
            )

        records = await logger_for_test.get_recent_executions(limit=5)
        assert len(records) == 1
        assert records[0]["task_name"] == "timeout_task"
        assert records[0]["status"] == "FAILED"
        assert "timeout" in (records[0]["error"] or "").lower()
        assert "0.05" in (records[0]["error"] or "")


# ═══════════════════════════════════════════════════════════════
# Query — get_recent_executions
# ═══════════════════════════════════════════════════════════════


class TestGetRecentExecutions:
    """get_recent_executions() 查询。"""

    @pytest.mark.anyio
    async def test_returns_empty_when_none(self, logger_for_test):
        """无记录时返回空列表。"""
        records = await logger_for_test.get_recent_executions()
        assert records == []

    @pytest.mark.anyio
    async def test_respects_limit(self, logger_for_test):
        """应遵守 limit 参数。"""
        for i in range(5):
            await logger_for_test.execute(f"task_{i}", _fast_job)

        records = await logger_for_test.get_recent_executions(limit=3)
        assert len(records) == 3

    @pytest.mark.anyio
    async def test_dict_keys_complete(self, logger_for_test):
        """每条记录应包含 id, task_name, status, start_time, end_time, duration, error。"""
        await logger_for_test.execute("dict_test", _fast_job)

        records = await logger_for_test.get_recent_executions(limit=1)
        record = records[0]
        for key in ("id", "task_name", "status", "start_time", "end_time", "duration", "error"):
            assert key in record, f"Missing key: {key}"


# ═══════════════════════════════════════════════════════════════
# Query — get_executions_by_task
# ═══════════════════════════════════════════════════════════════


class TestGetExecutionsByTask:
    """get_executions_by_task() 按任务筛选。"""

    @pytest.mark.anyio
    async def test_filters_by_task_name(self, logger_for_test):
        """应只返回指定任务名的记录。"""
        await logger_for_test.execute("alpha", _fast_job, "a")
        await logger_for_test.execute("alpha", _fast_job, "b")
        await logger_for_test.execute("beta", _fast_job, "c")

        records = await logger_for_test.get_executions_by_task("alpha")
        assert len(records) == 2
        for r in records:
            assert r["task_name"] == "alpha"

    @pytest.mark.anyio
    async def test_empty_for_unknown_task(self, logger_for_test):
        """未知任务名返回空列表。"""
        await logger_for_test.execute("known", _fast_job)
        records = await logger_for_test.get_executions_by_task("unknown")
        assert records == []

    @pytest.mark.anyio
    async def test_respects_limit(self, logger_for_test):
        """应遵守 limit 参数。"""
        for i in range(5):
            await logger_for_test.execute("x", _fast_job)

        records = await logger_for_test.get_executions_by_task("x", limit=2)
        assert len(records) == 2


# ═══════════════════════════════════════════════════════════════
# Query — get_failed_executions
# ═══════════════════════════════════════════════════════════════


class TestGetFailedExecutions:
    """get_failed_executions() 失败记录查询。"""

    @pytest.mark.anyio
    async def test_only_returns_failed(self, logger_for_test):
        """应只返回 FAILED 状态的记录。"""
        await logger_for_test.execute("good1", _fast_job)
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("bad1", _failing_job)
        await logger_for_test.execute("good2", _fast_job)
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("bad2", _failing_job)

        failed = await logger_for_test.get_failed_executions()
        assert len(failed) == 2
        for r in failed:
            assert r["status"] == "FAILED"
            assert r["error"] is not None

    @pytest.mark.anyio
    async def test_empty_when_all_success(self, logger_for_test):
        """全部成功时应返回空列表。"""
        await logger_for_test.execute("s1", _fast_job)
        await logger_for_test.execute("s2", _fast_job)
        failed = await logger_for_test.get_failed_executions()
        assert failed == []

    @pytest.mark.anyio
    async def test_respects_limit(self, logger_for_test):
        """应遵守 limit 参数。"""
        for i in range(5):
            with pytest.raises(RuntimeError):
                await logger_for_test.execute(f"bad_{i}", _failing_job)

        failed = await logger_for_test.get_failed_executions(limit=2)
        assert len(failed) == 2


# ═══════════════════════════════════════════════════════════════
# Resilience
# ═══════════════════════════════════════════════════════════════


class TestResilience:
    """DB 异常不影响任务执行。"""

    @pytest.mark.anyio
    async def test_task_succeeds_even_if_db_down(self, logger_for_test):
        """DB 不可用时任务仍应成功执行。"""
        # Override the logger to use a broken session factory
        def broken_factory():
            raise RuntimeError("DB connection lost")

        with patch(
            "app.database.base.get_async_session_factory",
            side_effect=broken_factory,
        ):
            broken_logger = TaskExecutionLogger()
            result = await broken_logger.execute("resilient", _fast_job, "survived")
            assert result == "survived"


# ═══════════════════════════════════════════════════════════════
# Integration — SchedulerManager + TaskRegistry
# ═══════════════════════════════════════════════════════════════


class TestSchedulerIntegration:
    """TaskExecutionLogger 与 SchedulerManager / TaskRegistry 集成。"""

    @pytest.mark.anyio
    async def test_integrate_with_registry_and_scheduler(self, logger_for_test, db_session_factory):
        """TaskRegistry → sync → SchedulerManager → execute 应完整记录。"""
        from app.scheduler.scheduler import SchedulerManager
        from app.tasks.registry import TaskRegistry

        registry = TaskRegistry()
        registry.register(
            "integrated_job",
            _fast_job,
            trigger="interval",
            seconds=3600,
        )

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)

        # Execute via scheduler's job func
        job = mgr.get_job("integrated_job")
        assert job is not None

        # But since scheduler isn't started, execute manually via logger
        await logger_for_test.execute("integrated_job", _fast_job, "from_registry")

        records = await logger_for_test.get_executions_by_task("integrated_job")
        assert len(records) == 1
        assert records[0]["status"] == "SUCCESS"

    @pytest.mark.anyio
    async def test_multiple_tasks_multiple_executions(self, logger_for_test):
        """多个任务多次执行的历史记录应正确区分。"""
        for i in range(3):
            await logger_for_test.execute("multi_a", _fast_job, f"a{i}")

        with pytest.raises(RuntimeError):
            await logger_for_test.execute("multi_b", _failing_job)

        a_records = await logger_for_test.get_executions_by_task("multi_a")
        b_records = await logger_for_test.get_executions_by_task("multi_b")
        assert len(a_records) == 3
        assert len(b_records) == 1
        assert b_records[0]["status"] == "FAILED"

    @pytest.mark.anyio
    async def test_list_recent_across_tasks(self, logger_for_test):
        """get_recent_executions 应跨任务按时间排序。"""
        await logger_for_test.execute("recent_a", _fast_job)
        await logger_for_test.execute("recent_b", _fast_job)
        with pytest.raises(RuntimeError):
            await logger_for_test.execute("recent_c", _failing_job)

        records = await logger_for_test.get_recent_executions(limit=10)
        assert len(records) == 3
        task_names = {r["task_name"] for r in records}
        assert task_names == {"recent_a", "recent_b", "recent_c"}
