"""Tests for Phase 9.7.6 — TaskExecution model and scheduler tracking.

Covers: TaskExecution ORM, TaskExecutionRepository, TaskScheduler.tracked_execute.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database.base import Base
from app.models.task_execution import TaskExecution
from app.database.task_execution_repository import TaskExecutionRepository


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ── TestTaskExecutionModel ─────────────────────────────────────


class TestTaskExecutionModel:
    """TaskExecution ORM model."""

    @pytest.mark.anyio
    async def test_create_basic(self, session):
        record = TaskExecution(task_name="daily_crawl")
        session.add(record)
        await session.flush()
        assert record.id is not None

    @pytest.mark.anyio
    async def test_defaults(self, session):
        record = TaskExecution(task_name="test_task")
        session.add(record)
        await session.flush()
        assert record.status == "RUNNING"
        assert record.duration is None
        assert record.error is None
        assert record.end_time is None

    @pytest.mark.anyio
    async def test_all_fields(self, session):
        record = TaskExecution(
            task_name="pipeline",
            status="SUCCESS",
            duration=120.5,
            error=None,
        )
        session.add(record)
        await session.flush()

        stmt = select(TaskExecution).where(TaskExecution.id == record.id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()
        assert fetched.task_name == "pipeline"
        assert fetched.status == "SUCCESS"
        assert fetched.duration == 120.5

    @pytest.mark.anyio
    async def test_repr(self):
        record = TaskExecution(id=1, task_name="test", status="SUCCESS")
        assert "TaskExecution" in repr(record)


# ── TestTaskExecutionRepository ────────────────────────────────


class TestTaskExecutionRepository:
    """TaskExecutionRepository CRUD."""

    @pytest.mark.anyio
    async def test_create(self, session):
        repo = TaskExecutionRepository(session)
        record = TaskExecution(task_name="daily_crawl")
        created = await repo.create(record)
        assert created.id is not None

    @pytest.mark.anyio
    async def test_finish_success(self, session):
        repo = TaskExecutionRepository(session)
        record = TaskExecution(task_name="test")
        created = await repo.create(record)

        finished = await repo.finish(
            created.id, status="SUCCESS", duration=60.0
        )
        assert finished is not None
        assert finished.status == "SUCCESS"
        assert finished.duration == 60.0
        assert finished.end_time is not None

    @pytest.mark.anyio
    async def test_finish_failed(self, session):
        repo = TaskExecutionRepository(session)
        record = TaskExecution(task_name="test")
        created = await repo.create(record)

        finished = await repo.finish(
            created.id, status="FAILED", error="timeout"
        )
        assert finished is not None
        assert finished.status == "FAILED"
        assert finished.error == "timeout"

    @pytest.mark.anyio
    async def test_finish_nonexistent(self, session):
        repo = TaskExecutionRepository(session)
        result = await repo.finish(9999, status="SUCCESS")
        assert result is None

    @pytest.mark.anyio
    async def test_get_recent(self, session):
        repo = TaskExecutionRepository(session)
        base = datetime(2026, 7, 19, 8, 0, 0)
        for i, name in enumerate(["task1", "task2", "task3"]):
            record = TaskExecution(
                task_name=name, start_time=base + timedelta(seconds=i)
            )
            await repo.create(record)

        records = await repo.get_recent(limit=2)
        assert len(records) == 2

    @pytest.mark.anyio
    async def test_get_by_task(self, session):
        repo = TaskExecutionRepository(session)
        base = datetime(2026, 7, 19, 8, 0, 0)
        for i in range(5):
            name = "crawl" if i < 3 else "pipeline"
            record = TaskExecution(
                task_name=name, start_time=base + timedelta(seconds=i)
            )
            await repo.create(record)

        records = await repo.get_by_task("crawl", limit=10)
        assert len(records) == 3
        for r in records:
            assert r.task_name == "crawl"


# ── TestSchedulerTrackedExecute ────────────────────────────────


class TestSchedulerTrackedExecute:
    """TaskScheduler.tracked_execute() wrapper."""

    @pytest.mark.anyio
    async def test_tracked_execute_success(self):
        """Successful execution returns result."""
        from app.tasks.scheduler import TaskScheduler

        func = AsyncMock(return_value="done")
        result = await TaskScheduler.tracked_execute("test_task", func, "arg1")
        assert result == "done"
        func.assert_called_once_with("arg1")

    @pytest.mark.anyio
    async def test_tracked_execute_raises(self):
        """Failed execution re-raises the exception."""
        from app.tasks.scheduler import TaskScheduler

        func = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await TaskScheduler.tracked_execute("test_task", func)
