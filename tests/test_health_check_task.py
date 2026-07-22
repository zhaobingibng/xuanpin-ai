"""Tests for Phase 44.3.1 — system_health_check task integration.

Covers:
- system_health_check() core: success, DB failure, scheduler states
- register_health_check_task() into TaskRegistry
- Closed loop: Registry → Sync → Execute → TaskExecution record
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.tasks.health_check_task import (
    register_health_check_task,
    system_health_check,
)
from app.tasks.registry import TaskRegistry


# ── Test helpers ───────────────────────────────────────────────


async def _delay(ms: float = 0.001) -> None:
    """Minimal async helper."""
    await asyncio.sleep(ms)


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite async session factory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════
# Core task — success
# ═══════════════════════════════════════════════════════════════


class TestSystemHealthCheckSuccess:
    """system_health_check() 正常成功场景。"""

    @pytest.mark.anyio
    async def test_returns_structured_result(self, db_session_factory):
        """应返回 status + timestamp + checks 三层结构。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check()

        assert isinstance(result, dict)
        assert "status" in result
        assert "timestamp" in result
        assert "checks" in result

    @pytest.mark.anyio
    async def test_status_healthy_when_db_ok(self, db_session_factory):
        """DB 正常且无 scheduler 时应返回 healthy。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check()

        assert result["status"] == "healthy"

    @pytest.mark.anyio
    async def test_database_check_ok(self, db_session_factory):
        """database.checks 应包含 status=ok。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check()

        assert result["checks"]["database"]["status"] == "ok"
        assert "SELECT 1" in result["checks"]["database"]["detail"]

    @pytest.mark.anyio
    async def test_time_check_has_iso_and_unix(self, db_session_factory):
        """time.checks 应包含 iso 字符串和 unix 浮点数。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check()

        time_check = result["checks"]["time"]
        assert isinstance(time_check["iso"], str)
        assert isinstance(time_check["unix"], float)
        assert time_check["unix"] > 0

    @pytest.mark.anyio
    async def test_timestamp_is_iso_format(self, db_session_factory):
        """timestamp 应是 ISO 8601 格式字符串。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check()

        ts = result["timestamp"]
        assert "T" in ts  # ISO format has T separator
        assert "+" in ts or "Z" in ts


# ═══════════════════════════════════════════════════════════════
# Core task — DB failure
# ═══════════════════════════════════════════════════════════════


class TestSystemHealthCheckDbFailure:
    """system_health_check() DB 异常场景。"""

    @pytest.mark.anyio
    async def test_unhealthy_when_db_fails(self):
        """DB 不可用时应返回 unhealthy。"""
        def broken_factory():
            raise RuntimeError("Cannot connect to database")

        with patch(
            "app.database.base.get_async_session_factory",
            side_effect=broken_factory,
        ):
            result = await system_health_check()

        assert result["status"] == "unhealthy"
        assert result["checks"]["database"]["status"] == "error"
        assert "Cannot connect" in result["checks"]["database"]["detail"]


# ═══════════════════════════════════════════════════════════════
# Core task — scheduler states
# ═══════════════════════════════════════════════════════════════


class TestSystemHealthCheckScheduler:
    """system_health_check() scheduler 状态检查。"""

    @pytest.mark.anyio
    async def test_scheduler_unknown_when_none(self, db_session_factory):
        """不传 scheduler 时应返回 unknown。"""
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check(scheduler=None)

        sc = result["checks"]["scheduler"]
        assert sc["status"] == "unknown"

    @pytest.mark.anyio
    async def test_scheduler_running_status(self, db_session_factory):
        """scheduler.running=True 时应返回 running。"""
        from unittest.mock import MagicMock

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.job_count = 3

        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check(scheduler=mock_scheduler)

        sc = result["checks"]["scheduler"]
        assert sc["status"] == "running"
        assert "3 job(s)" in sc["detail"]

    @pytest.mark.anyio
    async def test_scheduler_stopped_status(self, db_session_factory):
        """scheduler.running=False 时应返回 stopped。"""
        from unittest.mock import MagicMock

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check(scheduler=mock_scheduler)

        sc = result["checks"]["scheduler"]
        assert sc["status"] == "stopped"

    @pytest.mark.anyio
    async def test_scheduler_error_when_access_fails(self, db_session_factory):
        """访问 scheduler 抛异常时应返回 error 且整体为 degraded。"""
        from unittest.mock import MagicMock

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        # job_count access raises exception
        type(mock_scheduler).job_count = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Scheduler not reachable"))
        )

        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await system_health_check(scheduler=mock_scheduler)

        sc = result["checks"]["scheduler"]
        assert sc["status"] == "error"
        assert result["status"] == "degraded"


# ═══════════════════════════════════════════════════════════════
# Registry registration
# ═══════════════════════════════════════════════════════════════


class TestRegisterHealthCheckTask:
    """register_health_check_task() 注册流程。"""

    def test_registers_into_registry(self):
        """应在 TaskRegistry 中注册 system_health_check 任务。"""
        registry = TaskRegistry()
        td = register_health_check_task(registry)

        assert td is not None
        assert td.name == "system_health_check"
        assert td.trigger == "cron"
        assert td.trigger_kwargs == {"hour": 1, "minute": 0}
        assert td.enabled is True

    def test_registry_task_count_increments(self):
        """注册后 registry.task_count 应为 1。"""
        registry = TaskRegistry()
        assert registry.task_count == 0
        register_health_check_task(registry)
        assert registry.task_count == 1

    def test_registry_get_task_returns_definition(self):
        """registry.get_task 应返回正确的 TaskDefinition。"""
        registry = TaskRegistry()
        register_health_check_task(registry)

        td = registry.get_task("system_health_check")
        assert td is not None
        assert td.name == "system_health_check"
        assert td.func is not None

    def test_generated_func_is_callable(self):
        """注册的 func 应是 async callable。"""
        registry = TaskRegistry()
        td = register_health_check_task(registry)

        assert callable(td.func)
        assert asyncio.iscoroutinefunction(td.func)


# ═══════════════════════════════════════════════════════════════
# Scheduler sync
# ═══════════════════════════════════════════════════════════════


class TestSchedulerSync:
    """TaskRegistry → SchedulerManager 同步。"""

    def test_sync_adds_job_to_scheduler(self):
        """sync_to_scheduler 后 SchedulerManager 应包含该任务。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        register_health_check_task(registry)

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 1
        assert mgr.job_count == 1
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "system_health_check" in job_ids

    def test_sync_twice_is_idempotent(self):
        """两次 sync 不创建重复任务。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        register_health_check_task(registry)

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)
        registry.sync_to_scheduler(mgr)
        assert mgr.job_count == 1


# ═══════════════════════════════════════════════════════════════
# Full closed loop
# ═══════════════════════════════════════════════════════════════


class TestFullClosedLoop:
    """TaskRegistry → SchedulerManager → system_health_check → TaskExecution 闭环。"""

    @pytest.mark.anyio
    async def test_execute_via_registry_generates_execution_record(self, db_session_factory):
        """通过注册的 func 执行应产生 TaskExecution 记录。"""
        from app.scheduler.scheduler import SchedulerManager
        from app.tasks.execution_logger import TaskExecutionLogger

        registry = TaskRegistry()
        register_health_check_task(registry)

        scheduler_mgr = SchedulerManager()
        registry.sync_to_scheduler(scheduler_mgr)

        # Execute via the registered func directly (simulates scheduler triggering)
        td = registry.get_task("system_health_check")
        assert td is not None

        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            result = await td.func()

        assert isinstance(result, dict)
        assert "status" in result

        # Verify execution record exists
        exec_logger = TaskExecutionLogger()
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            records = await exec_logger.get_executions_by_task("system_health_check")
            assert len(records) == 1
            assert records[0]["status"] == "SUCCESS"

    @pytest.mark.anyio
    async def test_execution_record_has_duration(self, db_session_factory):
        """执行记录应包含 duration。"""
        from app.tasks.execution_logger import TaskExecutionLogger

        registry = TaskRegistry()
        register_health_check_task(registry)
        td = registry.get_task("system_health_check")

        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            await td.func()

        exec_logger = TaskExecutionLogger()
        with patch(
            "app.database.base.get_async_session_factory",
            return_value=db_session_factory,
        ):
            records = await exec_logger.get_executions_by_task("system_health_check")
            assert records[0]["duration"] is not None
            assert records[0]["duration"] >= 0
            assert records[0]["start_time"] is not None
            assert records[0]["end_time"] is not None

    @pytest.mark.anyio
    async def test_registry_list_includes_health_check(self, db_session_factory):
        """registry.list_tasks() 应包含 health check 任务。"""
        registry = TaskRegistry()
        register_health_check_task(registry)

        tasks = registry.list_tasks()
        task_names = {t["name"] for t in tasks}
        assert "system_health_check" in task_names
