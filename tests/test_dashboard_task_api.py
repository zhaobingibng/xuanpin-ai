"""Tests for Phase 45.3 — Dashboard 任务管理 API.

覆盖四个新端点：
- GET  /dashboard/tasks/definitions   → TaskRegistry.list_tasks
- GET  /dashboard/scheduler/jobs      → SchedulerManager.get_jobs
- GET  /dashboard/tasks/{name}/history→ DashboardService.get_task_history
- POST /dashboard/tasks/{name}/run    → TaskDefinition.func()（含 TaskExecutionLogger）

原则：不绕过 TaskExecutionLogger（手动执行必须走 td.func）；调度未就绪时优雅降级。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/tasks/definitions
# ═══════════════════════════════════════════════════════════════


class TestTaskDefinitions:
    @pytest.mark.anyio
    async def test_returns_registry_definitions(self):
        fake_registry = MagicMock()
        fake_registry.list_tasks.return_value = [
            {"name": "system_health_check", "trigger": "cron", "enabled": True},
            {"name": "daily_recommendation", "trigger": "cron", "enabled": True},
        ]
        with patch("app.api.main._task_registry", fake_registry):
            async with _client() as c:
                resp = await c.get("/dashboard/tasks/definitions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert {t["name"] for t in body} == {
            "system_health_check",
            "daily_recommendation",
        }

    @pytest.mark.anyio
    async def test_empty_when_registry_none(self):
        with patch("app.api.main._task_registry", None):
            async with _client() as c:
                resp = await c.get("/dashboard/tasks/definitions")
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/scheduler/jobs
# ═══════════════════════════════════════════════════════════════


class TestSchedulerJobs:
    @pytest.mark.anyio
    async def test_returns_manager_jobs(self):
        fake_mgr = MagicMock()
        fake_mgr.get_jobs.return_value = [
            {"id": "supplier_matching", "name": "supplier_matching",
             "next_run": "2026-07-22T04:00:00", "trigger": "cron"},
        ]
        with patch("app.api.main._scheduler_manager", fake_mgr):
            async with _client() as c:
                resp = await c.get("/dashboard/scheduler/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "supplier_matching"

    @pytest.mark.anyio
    async def test_empty_when_manager_none(self):
        with patch("app.api.main._scheduler_manager", None):
            async with _client() as c:
                resp = await c.get("/dashboard/scheduler/jobs")
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════
# GET /dashboard/tasks/{name}/history
# ═══════════════════════════════════════════════════════════════


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestTaskHistory:
    @pytest.mark.anyio
    async def test_returns_history(self):
        fake_svc = MagicMock()
        fake_svc.get_task_history = AsyncMock(
            return_value=[
                {"id": 2, "task_name": "supplier_matching", "status": "SUCCESS"},
                {"id": 1, "task_name": "supplier_matching", "status": "FAILED"},
            ]
        )
        with patch(
            "app.api.dashboard.get_async_session_factory",
            return_value=lambda: _FakeSession(),
        ), patch(
            "app.api.dashboard.DashboardService", return_value=fake_svc
        ):
            async with _client() as c:
                resp = await c.get(
                    "/dashboard/tasks/supplier_matching/history?limit=5"
                )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        fake_svc.get_task_history.assert_awaited_once_with(
            "supplier_matching", limit=5
        )

    @pytest.mark.anyio
    async def test_history_limit_validation(self):
        async with _client() as c:
            resp = await c.get("/dashboard/tasks/x/history?limit=0")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_history_error_returns_500(self):
        with patch(
            "app.api.dashboard.get_async_session_factory",
            side_effect=RuntimeError("db down"),
        ):
            async with _client() as c:
                resp = await c.get("/dashboard/tasks/x/history")
        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# POST /dashboard/tasks/{name}/run
# ═══════════════════════════════════════════════════════════════


class TestTaskRun:
    @pytest.mark.anyio
    async def test_run_goes_through_task_func(self):
        """手动执行必须调用 TaskDefinition.func()（内含 TaskExecutionLogger）。"""
        fake_func = AsyncMock(return_value={"status": "SUCCESS", "result": {"total": 3}})
        fake_td = MagicMock()
        fake_td.func = fake_func
        fake_registry = MagicMock()
        fake_registry.get_task.return_value = fake_td

        with patch("app.api.main._task_registry", fake_registry):
            async with _client() as c:
                resp = await c.post("/dashboard/tasks/supplier_matching/run")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["task_name"] == "supplier_matching"
        assert body["result"]["status"] == "SUCCESS"
        fake_func.assert_awaited_once()
        fake_registry.get_task.assert_called_once_with("supplier_matching")

    @pytest.mark.anyio
    async def test_run_unknown_task_returns_404(self):
        fake_registry = MagicMock()
        fake_registry.get_task.return_value = None
        with patch("app.api.main._task_registry", fake_registry):
            async with _client() as c:
                resp = await c.post("/dashboard/tasks/nope/run")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_run_when_registry_none_returns_503(self):
        with patch("app.api.main._task_registry", None):
            async with _client() as c:
                resp = await c.post("/dashboard/tasks/x/run")
        assert resp.status_code == 503

    @pytest.mark.anyio
    async def test_run_task_failure_returns_500(self):
        fake_td = MagicMock()
        fake_td.func = AsyncMock(side_effect=RuntimeError("boom"))
        fake_registry = MagicMock()
        fake_registry.get_task.return_value = fake_td
        with patch("app.api.main._task_registry", fake_registry):
            async with _client() as c:
                resp = await c.post("/dashboard/tasks/x/run")
        assert resp.status_code == 500
