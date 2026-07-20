"""Tests for Phase 10.1 — Task Timeout Management System.

Covers: TaskTimeoutManager, normal completion, timeout cancellation,
timeout recording, notification sending, metrics update, exception cases.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.task_timeout import TaskTimeoutError, TaskTimeoutManager
from app.services.metrics.service import SCHEDULER_TASK_FAILED_TOTAL


# ── Helpers ────────────────────────────────────────────────────


async def _quick_task(value: str = "done") -> str:
    """A task that completes quickly."""
    await asyncio.sleep(0.01)
    return value


async def _slow_task(duration: float = 10.0) -> str:
    """A task that takes too long."""
    await asyncio.sleep(duration)
    return "completed"


async def _failing_task() -> None:
    """A task that raises an exception."""
    raise RuntimeError("task error")


def _get_counter_value(counter) -> float:
    """Get current value of a counter."""
    return counter._value.get()


# ── TestTaskTimeoutManager ──────────────────────────────────────


class TestTaskTimeoutManager:
    """TaskTimeoutManager basic functionality."""

    def test_default_timeout(self):
        manager = TaskTimeoutManager()
        assert manager.default_timeout == 3600  # 1 hour

    def test_custom_default_timeout(self):
        manager = TaskTimeoutManager(default_timeout=600)
        assert manager.default_timeout == 600


# ── TestNormalCompletion ────────────────────────────────────────


class TestNormalCompletion:
    """Tasks that complete within timeout."""

    @pytest.mark.anyio
    async def test_task_completes_normally(self):
        manager = TaskTimeoutManager()
        result = await manager.execute_with_timeout(
            task_name="quick_task",
            func=_quick_task,
            timeout=5.0,
        )
        assert result == "done"

    @pytest.mark.anyio
    async def test_task_with_arguments(self):
        manager = TaskTimeoutManager()
        result = await manager.execute_with_timeout(
            task_name="arg_task",
            func=_quick_task,
            timeout=5.0,
            notify_on_timeout=False,
            record_failure=False,
            value="custom_value",
        )
        assert result == "custom_value"

    @pytest.mark.anyio
    async def test_task_uses_default_timeout(self):
        manager = TaskTimeoutManager(default_timeout=10.0)
        # Task should complete before default timeout
        result = await manager.execute_with_timeout(
            task_name="default_timeout_task",
            func=_quick_task,
            timeout=None,  # Uses default
        )
        assert result == "done"


# ── TestTimeoutCancellation ─────────────────────────────────────


class TestTimeoutCancellation:
    """Tasks that exceed timeout are cancelled."""

    @pytest.mark.anyio
    async def test_task_timeout_raises(self):
        manager = TaskTimeoutManager()
        with pytest.raises(TaskTimeoutError) as exc_info:
            await manager.execute_with_timeout(
                task_name="slow_task",
                func=_slow_task,
                timeout=0.05,  # Very short timeout
                notify_on_timeout=False,
                record_failure=False,
            )
        assert exc_info.value.task_name == "slow_task"
        assert exc_info.value.timeout_seconds == 0.05

    @pytest.mark.anyio
    async def test_timeout_error_message(self):
        manager = TaskTimeoutManager()
        with pytest.raises(TaskTimeoutError) as exc_info:
            await manager.execute_with_timeout(
                task_name="test_task",
                func=_slow_task,
                timeout=0.01,
                notify_on_timeout=False,
                record_failure=False,
            )
        assert "test_task" in str(exc_info.value)
        assert "0.01" in str(exc_info.value)


# ── TestMetricsUpdate ───────────────────────────────────────────


class TestMetricsUpdate:
    """Metrics are updated on timeout."""

    @pytest.mark.anyio
    async def test_metrics_increment_on_timeout(self):
        manager = TaskTimeoutManager()
        initial = _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL)

        with pytest.raises(TaskTimeoutError):
            await manager.execute_with_timeout(
                task_name="metrics_task",
                func=_slow_task,
                timeout=0.01,
                notify_on_timeout=False,
                record_failure=False,
            )

        assert _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL) == initial + 1

    @pytest.mark.anyio
    async def test_metrics_not_increment_on_success(self):
        manager = TaskTimeoutManager()
        initial = _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL)

        await manager.execute_with_timeout(
            task_name="success_task",
            func=_quick_task,
            timeout=5.0,
        )

        assert _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL) == initial


# ── TestNotificationSending ─────────────────────────────────────


class TestNotificationSending:
    """Notifications are sent on timeout."""

    @pytest.mark.anyio
    async def test_notification_sent_on_timeout(self):
        manager = TaskTimeoutManager()

        with patch("app.services.notification.service.NotificationService") as mock_cls:
            mock_notifier = MagicMock()
            mock_notifier.notify = AsyncMock()
            mock_cls.return_value = mock_notifier
            mock_cls.TASK_FAILED = "TASK_FAILED"

            with pytest.raises(TaskTimeoutError):
                await manager.execute_with_timeout(
                    task_name="notify_task",
                    func=_slow_task,
                    timeout=0.01,
                    notify_on_timeout=True,
                    record_failure=False,
                )

            mock_notifier.notify.assert_called_once()
            call_args = mock_notifier.notify.call_args
            assert call_args.kwargs["notification_type"] == "TASK_FAILED"
            assert "notify_task" in call_args.kwargs["message"]

    @pytest.mark.anyio
    async def test_notification_skipped_when_disabled(self):
        manager = TaskTimeoutManager()

        with patch("app.services.notification.service.NotificationService") as mock_cls:
            mock_notifier = MagicMock()
            mock_notifier.notify = AsyncMock()
            mock_cls.return_value = mock_notifier

            with pytest.raises(TaskTimeoutError):
                await manager.execute_with_timeout(
                    task_name="no_notify_task",
                    func=_slow_task,
                    timeout=0.01,
                    notify_on_timeout=False,
                    record_failure=False,
                )

            mock_notifier.notify.assert_not_called()


# ── TestTimeoutRecording ────────────────────────────────────────


class TestTimeoutRecording:
    """TaskExecution records are updated on timeout."""

    @pytest.mark.anyio
    async def test_failure_recorded_on_timeout(self):
        manager = TaskTimeoutManager()

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.get_by_task = AsyncMock(return_value=[])

        class _FakeCtx:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, *args):
                return False

        with patch("app.database.base.get_async_session_factory", return_value=MagicMock(return_value=_FakeCtx())):
            with patch("app.database.task_execution_repository.TaskExecutionRepository", return_value=mock_repo):
                with pytest.raises(TaskTimeoutError):
                    await manager.execute_with_timeout(
                        task_name="record_task",
                        func=_slow_task,
                        timeout=0.01,
                        notify_on_timeout=False,
                        record_failure=True,
                    )

    @pytest.mark.anyio
    async def test_failure_record_skipped_when_disabled(self):
        manager = TaskTimeoutManager()

        with patch("app.database.base.get_async_session_factory") as mock_factory:
            with pytest.raises(TaskTimeoutError):
                await manager.execute_with_timeout(
                    task_name="no_record_task",
                    func=_slow_task,
                    timeout=0.01,
                    notify_on_timeout=False,
                    record_failure=False,
                )

            # Factory should not be called when record_failure=False
            mock_factory.assert_not_called()


# ── TestExceptionCases ──────────────────────────────────────────


class TestExceptionCases:
    """Edge cases and exception handling."""

    @pytest.mark.anyio
    async def test_task_raises_non_timeout_exception(self):
        manager = TaskTimeoutManager()
        with pytest.raises(RuntimeError) as exc_info:
            await manager.execute_with_timeout(
                task_name="failing_task",
                func=_failing_task,
                timeout=5.0,
            )
        assert "task error" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_zero_timeout(self):
        manager = TaskTimeoutManager()
        # Zero timeout should raise immediately
        with pytest.raises(TaskTimeoutError):
            await manager.execute_with_timeout(
                task_name="zero_timeout",
                func=_quick_task,
                timeout=0,
                notify_on_timeout=False,
                record_failure=False,
            )

    @pytest.mark.anyio
    async def test_notification_failure_does_not_raise(self):
        manager = TaskTimeoutManager()

        with patch("app.services.notification.service.NotificationService") as mock_cls:
            mock_cls.side_effect = RuntimeError("notification error")

            # Should not raise notification error
            with pytest.raises(TaskTimeoutError):
                await manager.execute_with_timeout(
                    task_name="notify_fail_task",
                    func=_slow_task,
                    timeout=0.01,
                    notify_on_timeout=True,
                    record_failure=False,
                )

    @pytest.mark.anyio
    async def test_metrics_failure_does_not_raise(self):
        manager = TaskTimeoutManager()

        with patch("app.services.metrics.service.MetricsService.inc_scheduler_task_failed") as mock_inc:
            mock_inc.side_effect = RuntimeError("metrics error")

            # Should not raise metrics error
            with pytest.raises(TaskTimeoutError):
                await manager.execute_with_timeout(
                    task_name="metrics_fail_task",
                    func=_slow_task,
                    timeout=0.01,
                    notify_on_timeout=False,
                    record_failure=False,
                )


# ── TestSchedulerIntegration ────────────────────────────────────


class TestSchedulerIntegration:
    """TaskScheduler.tracked_execute with timeout."""

    @pytest.mark.anyio
    async def test_tracked_execute_with_timeout(self):
        from app.tasks.scheduler import TaskScheduler

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=MagicMock(id=1))
        mock_repo.finish = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, *args):
                return False

        with patch("app.database.base.get_async_session_factory", return_value=MagicMock(return_value=_FakeCtx())):
            with patch("app.database.task_execution_repository.TaskExecutionRepository", return_value=mock_repo):
                with patch("app.models.task_execution.TaskExecution"):
                    result = await TaskScheduler.tracked_execute(
                        task_name="timeout_test",
                        func=_quick_task,
                        timeout=5.0,
                    )
                    assert result == "done"

    @pytest.mark.anyio
    async def test_tracked_execute_timeout_raises(self):
        from app.tasks.scheduler import TaskScheduler

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=MagicMock(id=1))
        mock_repo.finish = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, *args):
                return False

        with patch("app.database.base.get_async_session_factory", return_value=MagicMock(return_value=_FakeCtx())):
            with patch("app.database.task_execution_repository.TaskExecutionRepository", return_value=mock_repo):
                with patch("app.models.task_execution.TaskExecution"):
                    with pytest.raises(asyncio.TimeoutError):
                        await TaskScheduler.tracked_execute(
                            task_name="timeout_fail_test",
                            func=_slow_task,
                            timeout=0.01,
                        )


# ── TestTaskTimeoutError ────────────────────────────────────────


class TestTaskTimeoutError:
    """TaskTimeoutError exception class."""

    def test_error_attributes(self):
        error = TaskTimeoutError("test_task", 300.0)
        assert error.task_name == "test_task"
        assert error.timeout_seconds == 300.0

    def test_error_message(self):
        error = TaskTimeoutError("crawl_job", 600.0)
        assert "crawl_job" in str(error)
        assert "600" in str(error)

    def test_error_is_exception(self):
        error = TaskTimeoutError("test", 1.0)
        assert isinstance(error, Exception)
