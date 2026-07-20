"""Tests for Phase 10.2 — Failed Task Queue.

Covers: FailedTask model, FailedTaskRepository, TaskQueueService,
Tasks API, metrics integration, notification integration, exception cases.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.failed_task import (
    FailedTask,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RETRYING,
    VALID_STATUSES,
)


# ── Helpers ────────────────────────────────────────────────────


def _make_task(
    id: int = 1,
    task_name: str = "test_task",
    payload: str | None = None,
    error: str | None = "test error",
    exception_type: str | None = "RuntimeError",
    retry_count: int = 0,
    max_retry: int = 3,
    status: str = STATUS_PENDING,
) -> FailedTask:
    task = FailedTask(
        task_name=task_name,
        payload=payload,
        error=error,
        exception_type=exception_type,
        retry_count=retry_count,
        max_retry=max_retry,
        status=status,
    )
    task.id = id
    task.created_at = datetime(2026, 7, 19, 10, 0, 0)
    task.updated_at = datetime(2026, 7, 19, 10, 0, 0)
    return task


# ── TestFailedTaskModel ─────────────────────────────────────────


class TestFailedTaskModel:
    """FailedTask model tests."""

    def test_create_failed_task(self):
        task = FailedTask(
            task_name="crawl_job",
            payload='{"keyword": "test"}',
            error="Connection timeout",
            exception_type="TimeoutError",
            retry_count=0,
            max_retry=3,
            status=STATUS_PENDING,
        )
        assert task.task_name == "crawl_job"
        assert task.payload == '{"keyword": "test"}'
        assert task.error == "Connection timeout"
        assert task.exception_type == "TimeoutError"
        assert task.retry_count == 0
        assert task.max_retry == 3
        assert task.status == STATUS_PENDING

    def test_default_values(self):
        task = FailedTask(task_name="test")
        # Note: SQLAlchemy defaults are None until persisted unless set explicitly
        assert task.retry_count is None or task.retry_count == 0
        assert task.max_retry is None or task.max_retry == 3
        assert task.status is None or task.status == STATUS_PENDING

    def test_repr(self):
        task = _make_task()
        repr_str = repr(task)
        assert "FailedTask" in repr_str
        assert "test_task" in repr_str
        assert STATUS_PENDING in repr_str

    def test_can_retry_pending(self):
        task = _make_task(status=STATUS_PENDING, retry_count=0, max_retry=3)
        assert task.can_retry() is True

    def test_can_retry_failed(self):
        task = _make_task(status=STATUS_FAILED, retry_count=1, max_retry=3)
        assert task.can_retry() is True

    def test_cannot_retry_resolved(self):
        task = _make_task(status=STATUS_RESOLVED, retry_count=0, max_retry=3)
        assert task.can_retry() is False

    def test_cannot_retry_retrying(self):
        task = _make_task(status=STATUS_RETRYING, retry_count=0, max_retry=3)
        assert task.can_retry() is False

    def test_cannot_retry_max_reached(self):
        task = _make_task(status=STATUS_PENDING, retry_count=3, max_retry=3)
        assert task.can_retry() is False

    def test_status_constants(self):
        assert STATUS_PENDING == "PENDING"
        assert STATUS_RETRYING == "RETRYING"
        assert STATUS_FAILED == "FAILED"
        assert STATUS_RESOLVED == "RESOLVED"

    def test_valid_statuses(self):
        assert STATUS_PENDING in VALID_STATUSES
        assert STATUS_RETRYING in VALID_STATUSES
        assert STATUS_FAILED in VALID_STATUSES
        assert STATUS_RESOLVED in VALID_STATUSES


# ── TestFailedTaskRepository ────────────────────────────────────


class TestFailedTaskRepository:
    """FailedTaskRepository tests."""

    @pytest.mark.anyio
    async def test_create(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        repo = FailedTaskRepository(session)
        task = FailedTask(task_name="test_task", error="test error")
        result = await repo.create(task)

        session.add.assert_called_once_with(task)
        assert result == task

    @pytest.mark.anyio
    async def test_get_by_id(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        expected_task = _make_task(id=1)
        session.get = AsyncMock(return_value=expected_task)

        repo = FailedTaskRepository(session)
        result = await repo.get_by_id(1)

        session.get.assert_called_once_with(FailedTask, 1)
        assert result == expected_task

    @pytest.mark.anyio
    async def test_get_by_id_not_found(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        repo = FailedTaskRepository(session)
        result = await repo.get_by_id(999)

        assert result is None

    @pytest.mark.anyio
    async def test_get_failed(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        tasks = [_make_task(id=1), _make_task(id=2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = tasks
        session.execute = AsyncMock(return_value=mock_result)

        repo = FailedTaskRepository(session)
        result = await repo.get_failed(limit=10)

        assert len(result) == 2

    @pytest.mark.anyio
    async def test_get_failed_with_status_filter(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        tasks = [_make_task(id=1, status=STATUS_PENDING)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = tasks
        session.execute = AsyncMock(return_value=mock_result)

        repo = FailedTaskRepository(session)
        result = await repo.get_failed(status=STATUS_PENDING, limit=10)

        assert len(result) == 1

    @pytest.mark.anyio
    async def test_get_pending(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        tasks = [_make_task(id=1, status=STATUS_PENDING, retry_count=0)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = tasks
        session.execute = AsyncMock(return_value=mock_result)

        repo = FailedTaskRepository(session)
        result = await repo.get_pending(limit=10)

        assert len(result) == 1

    @pytest.mark.anyio
    async def test_update_status(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_PENDING)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        repo = FailedTaskRepository(session)
        result = await repo.update_status(1, STATUS_RETRYING, increment_retry=True)

        assert result.status == STATUS_RETRYING
        assert result.retry_count == 1
        session.flush.assert_called_once()

    @pytest.mark.anyio
    async def test_mark_retrying(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_PENDING, retry_count=0)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        repo = FailedTaskRepository(session)
        result = await repo.mark_retrying(1)

        assert result.status == STATUS_RETRYING
        assert result.retry_count == 1

    @pytest.mark.anyio
    async def test_mark_resolved(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_RETRYING)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        repo = FailedTaskRepository(session)
        result = await repo.mark_resolved(1)

        assert result.status == STATUS_RESOLVED

    @pytest.mark.anyio
    async def test_mark_failed(self):
        from app.database.failed_task_repository import FailedTaskRepository

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_RETRYING)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        repo = FailedTaskRepository(session)
        result = await repo.mark_failed(1, error="Final failure")

        assert result.status == STATUS_FAILED
        assert result.error == "Final failure"


# ── TestTaskQueueService ────────────────────────────────────────


class TestTaskQueueService:
    """TaskQueueService tests."""

    @pytest.mark.anyio
    async def test_record_failure(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch("app.services.notification.service.NotificationService") as mock_notif_cls:
            mock_notifier = MagicMock()
            mock_notifier.notify = AsyncMock()
            mock_notif_cls.return_value = mock_notifier

            svc = TaskQueueService(session)
            task = await svc.record_failure(
                task_name="test_task",
                error="Test error",
                exception_type="RuntimeError",
                payload={"key": "value"},
                max_retry=5,
            )

            assert task.task_name == "test_task"
            assert task.error == "Test error"
            assert task.exception_type == "RuntimeError"
            assert task.max_retry == 5
            assert task.status == STATUS_PENDING
            assert task.payload == '{"key": "value"}'
            mock_notifier.notify.assert_called_once()

    @pytest.mark.anyio
    async def test_record_failure_notification_error(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch("app.services.notification.service.NotificationService") as mock_notif_cls:
            mock_notif_cls.side_effect = RuntimeError("notification error")

            svc = TaskQueueService(session)
            task = await svc.record_failure(
                task_name="test_task",
                error="Test error",
            )

            # Should still create task even if notification fails
            assert task.task_name == "test_task"

    @pytest.mark.anyio
    async def test_retry_task_success(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_PENDING, retry_count=0, max_retry=3)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        async def success_func():
            return "success"

        svc = TaskQueueService(session)
        success, result_task = await svc.retry_task(1, success_func)

        assert success is True
        assert result_task.status == STATUS_RESOLVED

    @pytest.mark.anyio
    async def test_retry_task_failure_can_retry(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_PENDING, retry_count=1, max_retry=3)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        async def fail_func():
            raise RuntimeError("still failing")

        svc = TaskQueueService(session)
        success, result_task = await svc.retry_task(1, fail_func)

        assert success is False
        assert result_task.status == STATUS_PENDING  # Can still retry
        assert "Retry 2 failed" in result_task.error

    @pytest.mark.anyio
    async def test_retry_task_failure_max_reached(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_PENDING, retry_count=2, max_retry=3)
        session.get = AsyncMock(return_value=task)
        session.flush = AsyncMock()

        async def fail_func():
            raise RuntimeError("final failure")

        svc = TaskQueueService(session)
        success, result_task = await svc.retry_task(1, fail_func)

        assert success is False
        assert result_task.status == STATUS_FAILED  # Max retries reached

    @pytest.mark.anyio
    async def test_retry_task_not_found(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        async def some_func():
            return "result"

        svc = TaskQueueService(session)
        success, result = await svc.retry_task(999, some_func)

        assert success is False
        assert result is None

    @pytest.mark.anyio
    async def test_retry_task_cannot_retry(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        task = _make_task(id=1, status=STATUS_RESOLVED, retry_count=3, max_retry=3)
        session.get = AsyncMock(return_value=task)

        async def some_func():
            return "result"

        svc = TaskQueueService(session)
        success, result = await svc.retry_task(1, some_func)

        assert success is False
        assert result == task

    @pytest.mark.anyio
    async def test_get_failed_tasks(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        tasks = [_make_task(id=1), _make_task(id=2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = tasks
        session.execute = AsyncMock(return_value=mock_result)

        svc = TaskQueueService(session)
        result = await svc.get_failed_tasks(status=None, limit=50)

        assert len(result) == 2

    @pytest.mark.anyio
    async def test_get_task(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        expected_task = _make_task(id=1)
        session.get = AsyncMock(return_value=expected_task)

        svc = TaskQueueService(session)
        result = await svc.get_task(1)

        assert result == expected_task


# ── TestTasksAPI ────────────────────────────────────────────────


class _FakeSessionCtx:
    """Fake async context manager for session factory."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


class TestTasksAPI:
    """Tasks API endpoint tests."""

    @pytest.mark.anyio
    async def test_get_failed_tasks_endpoint(self):
        from app.api.tasks import get_failed_tasks

        mock_task = _make_task(id=1, task_name="test_task", status=STATUS_PENDING)
        mock_session = AsyncMock()

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            with patch.object(
                mock_session, "execute",
                new_callable=AsyncMock,
                return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_task]))))
            ):
                result = await get_failed_tasks(status=None, limit=50)

        assert len(result) == 1
        assert result[0]["task_name"] == "test_task"

    @pytest.mark.anyio
    async def test_get_failed_task_endpoint(self):
        from app.api.tasks import get_failed_task

        mock_task = _make_task(id=1, task_name="test_task")
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_task)

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            result = await get_failed_task(task_id=1)

        assert result["id"] == 1
        assert result["task_name"] == "test_task"

    @pytest.mark.anyio
    async def test_get_failed_task_not_found(self):
        from app.api.tasks import get_failed_task
        from fastapi import HTTPException

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            with pytest.raises(HTTPException) as exc_info:
                await get_failed_task(task_id=999)
            assert exc_info.value.status_code == 404

    @pytest.mark.anyio
    async def test_retry_failed_task_endpoint(self):
        from app.api.tasks import retry_failed_task

        mock_task = _make_task(id=1, status=STATUS_PENDING, retry_count=0, max_retry=3)
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_task)
        mock_session.flush = AsyncMock()

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            result = await retry_failed_task(task_id=1)

        assert "message" in result
        assert result["task"]["id"] == 1
        assert result["task"]["status"] == STATUS_RETRYING

    @pytest.mark.anyio
    async def test_retry_failed_task_not_found(self):
        from app.api.tasks import retry_failed_task
        from fastapi import HTTPException

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            with pytest.raises(HTTPException) as exc_info:
                await retry_failed_task(task_id=999)
            assert exc_info.value.status_code == 404

    @pytest.mark.anyio
    async def test_retry_failed_task_cannot_retry(self):
        from app.api.tasks import retry_failed_task
        from fastapi import HTTPException

        mock_task = _make_task(id=1, status=STATUS_RESOLVED, retry_count=3, max_retry=3)
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_task)

        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.tasks.get_async_session_factory", return_value=fake_factory):
            with pytest.raises(HTTPException) as exc_info:
                await retry_failed_task(task_id=1)
            assert exc_info.value.status_code == 400


# ── TestRecoveryManagerIntegration ──────────────────────────────


class TestRecoveryManagerIntegration:
    """Test RecoveryManager integration with FailedTask."""

    @pytest.mark.anyio
    async def test_recovery_creates_failed_task(self):
        from app.core.recovery import RecoveryManager

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self_inner):
                return mock_session
            async def __aexit__(self_inner, *args):
                return False

        async def failing_func():
            raise RuntimeError("test error")

        recovery = RecoveryManager(max_retries=2, retry_delay=0)

        with patch("app.database.base.get_async_session_factory", return_value=MagicMock(return_value=_FakeCtx())):
            with patch("app.services.notification.service.NotificationService") as mock_notif:
                mock_notif.return_value.notify = AsyncMock()
                result = await recovery.execute(
                    failing_func,
                    category="test",
                    task_name="test_task",
                )

        assert result is None
        # Verify FailedTask was created
        mock_session.add.assert_called()


# ── TestExceptionCases ──────────────────────────────────────────


class TestExceptionCases:
    """Edge cases and exception handling."""

    def test_invalid_status_constant(self):
        assert "INVALID" not in VALID_STATUSES

    @pytest.mark.anyio
    async def test_empty_payload(self):
        from app.services.task_queue.service import TaskQueueService

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch("app.services.notification.service.NotificationService") as mock_notif_cls:
            mock_notifier = MagicMock()
            mock_notifier.notify = AsyncMock()
            mock_notif_cls.return_value = mock_notifier

            svc = TaskQueueService(session)
            task = await svc.record_failure(
                task_name="test_task",
                error="Test error",
                payload=None,
            )

            assert task.payload is None
