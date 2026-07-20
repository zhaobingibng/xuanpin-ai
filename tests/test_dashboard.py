"""Tests for Phase 9.9 — Dashboard API for system operations.

Covers: system_overview, tasks, notifications, logs, empty data, exceptions, API responses.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dashboard.service import DashboardService, _notification_history


# ── Helpers ────────────────────────────────────────────────────


class _FakeSessionCtx:
    """Fake async context manager for session factory."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _make_session():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    return session


def _make_task_execution(
    id: int = 1,
    task_name: str = "test_task",
    status: str = "SUCCESS",
    duration: float = 1.5,
    error: str | None = None,
):
    task = MagicMock()
    task.id = id
    task.task_name = task_name
    task.start_time = datetime(2026, 7, 19, 10, 0, 0)
    task.end_time = datetime(2026, 7, 19, 10, 0, 1)
    task.status = status
    task.duration = duration
    task.error = error
    return task


# ── TestSystemOverview ──────────────────────────────────────────


class TestSystemOverview:
    """DashboardService.system_overview() returns correct system status."""

    @pytest.mark.anyio
    async def test_system_overview_structure(self):
        session = _make_session()
        svc = DashboardService(session)

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=[])

            with patch("app.services.health.service.HealthService") as mock_health_cls:
                mock_health = MagicMock()
                mock_health.check = AsyncMock(return_value={
                    "status": "healthy",
                    "database": True,
                    "crawler": True,
                    "scheduler": True,
                    "last_crawl": None,
                })
                mock_health_cls.return_value = mock_health

                with patch("app.api.main._scheduler_instance", None):
                    result = await svc.system_overview()

        assert "health" in result
        assert "uptime_seconds" in result
        assert "task_stats" in result
        assert "crawler_status" in result
        assert "scheduler_status" in result

    @pytest.mark.anyio
    async def test_system_overview_task_stats(self):
        session = _make_session()
        svc = DashboardService(session)

        tasks = [
            _make_task_execution(id=1, status="SUCCESS"),
            _make_task_execution(id=2, status="SUCCESS"),
            _make_task_execution(id=3, status="FAILED"),
        ]

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=tasks)

            with patch("app.services.health.service.HealthService") as mock_health_cls:
                mock_health = MagicMock()
                mock_health.check = AsyncMock(return_value={
                    "status": "warning",
                    "database": True,
                    "crawler": True,
                    "scheduler": True,
                    "last_crawl": None,
                })
                mock_health_cls.return_value = mock_health

                with patch("app.api.main._scheduler_instance", None):
                    result = await svc.system_overview()

        assert result["task_stats"]["total"] == 3
        assert result["task_stats"]["failed"] == 1
        assert result["task_stats"]["success_rate"] == pytest.approx(66.67, abs=0.01)

    @pytest.mark.anyio
    async def test_system_overview_empty_tasks(self):
        session = _make_session()
        svc = DashboardService(session)

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=[])

            with patch("app.services.health.service.HealthService") as mock_health_cls:
                mock_health = MagicMock()
                mock_health.check = AsyncMock(return_value={
                    "status": "healthy",
                    "database": True,
                    "crawler": True,
                    "scheduler": True,
                    "last_crawl": None,
                })
                mock_health_cls.return_value = mock_health

                with patch("app.api.main._scheduler_instance", None):
                    result = await svc.system_overview()

        assert result["task_stats"]["total"] == 0
        assert result["task_stats"]["success_rate"] == 100.0


# ── TestRecentTasks ─────────────────────────────────────────────


class TestRecentTasks:
    """DashboardService.get_recent_tasks() returns task records."""

    @pytest.mark.anyio
    async def test_get_recent_tasks(self):
        session = _make_session()
        svc = DashboardService(session)

        tasks = [
            _make_task_execution(id=1, task_name="crawl_job", status="SUCCESS", duration=2.5),
            _make_task_execution(id=2, task_name="pipeline_job", status="FAILED", duration=1.0, error="timeout"),
        ]

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=tasks)
            result = await svc.get_recent_tasks(limit=10)

        assert len(result) == 2
        assert result[0]["task_name"] == "crawl_job"
        assert result[0]["status"] == "SUCCESS"
        assert result[0]["duration"] == 2.5
        assert result[1]["error"] == "timeout"

    @pytest.mark.anyio
    async def test_get_recent_tasks_empty(self):
        session = _make_session()
        svc = DashboardService(session)

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=[])
            result = await svc.get_recent_tasks()

        assert result == []

    @pytest.mark.anyio
    async def test_get_recent_tasks_limit(self):
        session = _make_session()
        svc = DashboardService(session)

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(return_value=[])
            await svc.get_recent_tasks(limit=5)
            mock_task_repo.get_recent.assert_called_once_with(limit=5)


# ── TestNotifications ───────────────────────────────────────────


class TestNotifications:
    """DashboardService.get_notifications() returns notification history."""

    def setup_method(self):
        """Clear notification history before each test."""
        _notification_history.clear()

    def test_get_notifications_empty(self):
        session = _make_session()
        svc = DashboardService(session)
        result = svc.get_notifications()
        assert result == []

    def test_get_notifications_with_data(self):
        session = _make_session()
        svc = DashboardService(session)

        # Add some notifications
        _notification_history.extend([
            {"type": "CRAWL_FAILED", "message": "test1", "timestamp": "2026-07-19T10:00:00"},
            {"type": "SYSTEM_ERROR", "message": "test2", "timestamp": "2026-07-19T10:01:00"},
        ])

        result = svc.get_notifications()
        assert len(result) == 2
        assert result[0]["type"] == "CRAWL_FAILED"

    def test_get_notifications_limit(self):
        session = _make_session()
        svc = DashboardService(session)

        # Add 10 notifications
        for i in range(10):
            _notification_history.append({"type": f"TYPE_{i}", "message": f"msg_{i}"})

        result = svc.get_notifications(limit=5)
        assert len(result) == 5
        # Should be the last 5
        assert result[0]["type"] == "TYPE_5"


# ── TestLogs ────────────────────────────────────────────────────


class TestLogs:
    """DashboardService.get_logs() reads log files correctly."""

    def test_get_logs_nonexistent_file(self):
        session = _make_session()
        svc = DashboardService(session)
        result = svc.get_logs(log_file="nonexistent.log", log_dir="/tmp")
        assert result == []

    def test_get_logs_with_temp_file(self):
        session = _make_session()
        svc = DashboardService(session)

        # Create temp log file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
            temp_path = f.name

        try:
            log_dir = str(Path(temp_path).parent)
            log_file = Path(temp_path).name
            result = svc.get_logs(log_file=log_file, log_dir=log_dir, limit=10)

            assert len(result) == 5
            # Newest first (reversed)
            assert result[0] == "Line 5"
            assert result[-1] == "Line 1"
        finally:
            Path(temp_path).unlink()

    def test_get_logs_limit(self):
        session = _make_session()
        svc = DashboardService(session)

        # Create temp log file with many lines
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(20):
                f.write(f"Line {i+1}\n")
            temp_path = f.name

        try:
            log_dir = str(Path(temp_path).parent)
            log_file = Path(temp_path).name
            result = svc.get_logs(log_file=log_file, log_dir=log_dir, limit=5)

            assert len(result) == 5
            # Should be last 5 lines, reversed
            assert result[0] == "Line 20"
            assert result[-1] == "Line 16"
        finally:
            Path(temp_path).unlink()


# ── TestDashboardAPI ────────────────────────────────────────────


class TestDashboardAPI:
    """Dashboard API endpoints return correct responses."""

    @pytest.mark.anyio
    async def test_dashboard_system_endpoint(self):
        from app.api.dashboard import dashboard_system

        fake_result = {
            "health": {"status": "healthy"},
            "uptime_seconds": 0,
            "task_stats": {"total": 10, "failed": 1, "success_rate": 90.0},
            "crawler_status": True,
            "scheduler_status": True,
        }

        mock_session = _make_session()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.dashboard.get_async_session_factory", return_value=fake_factory):
            with patch.object(DashboardService, "system_overview", new_callable=AsyncMock, return_value=fake_result):
                result = await dashboard_system()

        assert result["health"]["status"] == "healthy"
        assert result["task_stats"]["total"] == 10

    @pytest.mark.anyio
    async def test_dashboard_tasks_endpoint(self):
        from app.api.dashboard import dashboard_tasks

        fake_tasks = [
            {"id": 1, "task_name": "test", "status": "SUCCESS", "duration": 1.0, "error": None},
        ]

        mock_session = _make_session()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.dashboard.get_async_session_factory", return_value=fake_factory):
            with patch.object(DashboardService, "get_recent_tasks", new_callable=AsyncMock, return_value=fake_tasks):
                result = await dashboard_tasks(limit=10)

        assert len(result) == 1
        assert result[0]["task_name"] == "test"

    @pytest.mark.anyio
    async def test_dashboard_notifications_endpoint(self):
        from app.api.dashboard import dashboard_notifications

        fake_notifications = [
            {"type": "CRAWL_FAILED", "message": "test"},
        ]

        mock_session = _make_session()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.dashboard.get_async_session_factory", return_value=fake_factory):
            with patch.object(DashboardService, "get_notifications", return_value=fake_notifications):
                result = await dashboard_notifications(limit=10)

        assert len(result) == 1
        assert result[0]["type"] == "CRAWL_FAILED"

    @pytest.mark.anyio
    async def test_dashboard_logs_endpoint(self):
        from app.api.dashboard import dashboard_logs

        fake_logs = ["Log line 1", "Log line 2"]

        mock_session = _make_session()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.dashboard.get_async_session_factory", return_value=fake_factory):
            with patch.object(DashboardService, "get_logs", return_value=fake_logs):
                result = await dashboard_logs(file="app.log", limit=100)

        assert len(result) == 2
        assert result[0] == "Log line 1"


# ── TestExceptionCases ──────────────────────────────────────────


class TestExceptionCases:
    """Dashboard handles exceptions gracefully."""

    @pytest.mark.anyio
    async def test_system_overview_exception(self):
        session = _make_session()
        svc = DashboardService(session)

        with patch.object(svc, "_task_repo") as mock_task_repo:
            mock_task_repo.get_recent = AsyncMock(side_effect=RuntimeError("db error"))

            with patch("app.services.health.service.HealthService") as mock_health_cls:
                mock_health_cls.return_value.check = AsyncMock(return_value={"status": "error"})

                with patch("app.api.main._scheduler_instance", None):
                    # Should raise or handle gracefully
                    with pytest.raises(RuntimeError):
                        await svc.system_overview()

    @pytest.mark.anyio
    async def test_tasks_endpoint_exception(self):
        from app.api.dashboard import dashboard_tasks
        from fastapi import HTTPException

        mock_session = _make_session()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.dashboard.get_async_session_factory", return_value=fake_factory):
            with patch.object(DashboardService, "get_recent_tasks", new_callable=AsyncMock, side_effect=RuntimeError("error")):
                with pytest.raises(HTTPException) as exc_info:
                    await dashboard_tasks(limit=10)
                assert exc_info.value.status_code == 500

    def test_logs_file_permission_error(self):
        session = _make_session()
        svc = DashboardService(session)

        # Try to read a file that causes permission error
        with patch("builtins.open", side_effect=PermissionError("access denied")):
            result = svc.get_logs(log_file="app.log", log_dir="/restricted")
            assert result == []
