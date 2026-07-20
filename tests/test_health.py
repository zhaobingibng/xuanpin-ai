"""Tests for Phase 9.7.6 — HealthService and system health API.

Covers: HealthService.check(), database/crawler/scheduler detection, /system/health API.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.health.service import (
    HealthService,
    SYSTEM_HEALTHY,
    SYSTEM_WARNING,
    SYSTEM_ERROR,
)


# ── Helpers ────────────────────────────────────────────────────


class _FakeSessionCtx:
    """Fake async context manager for session factory."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _make_session(db_ok: bool = True):
    session = AsyncMock()
    if db_ok:
        session.execute = AsyncMock(return_value=MagicMock())
    else:
        session.execute = AsyncMock(side_effect=RuntimeError("db error"))
    return session


# ── TestHealthService ──────────────────────────────────────────


class TestHealthService:
    """HealthService.check() returns correct health status."""

    @pytest.mark.anyio
    async def test_all_healthy(self):
        session = _make_session(db_ok=True)
        svc = HealthService(session, scheduler_running=True)

        with patch.object(svc, "_check_crawler", return_value={"ok": True, "last_crawl": "2026-07-19"}):
            result = await svc.check()

        assert result["status"] == SYSTEM_HEALTHY
        assert result["database"] is True
        assert result["scheduler"] is True
        assert result["crawler"] is True

    @pytest.mark.anyio
    async def test_database_down(self):
        session = _make_session(db_ok=False)
        svc = HealthService(session, scheduler_running=True)

        with patch.object(svc, "_check_crawler", return_value={"ok": True, "last_crawl": None}):
            result = await svc.check()

        assert result["status"] == SYSTEM_ERROR
        assert result["database"] is False

    @pytest.mark.anyio
    async def test_scheduler_down(self):
        session = _make_session(db_ok=True)
        svc = HealthService(session, scheduler_running=False)

        with patch.object(svc, "_check_crawler", return_value={"ok": True, "last_crawl": None}):
            result = await svc.check()

        assert result["status"] == SYSTEM_WARNING
        assert result["scheduler"] is False

    @pytest.mark.anyio
    async def test_crawler_failed(self):
        session = _make_session(db_ok=True)
        svc = HealthService(session, scheduler_running=True)

        with patch.object(svc, "_check_crawler", return_value={"ok": False, "last_crawl": "2026-07-18"}):
            result = await svc.check()

        assert result["status"] == SYSTEM_WARNING
        assert result["crawler"] is False

    @pytest.mark.anyio
    async def test_check_database_success(self):
        session = _make_session(db_ok=True)
        svc = HealthService(session)
        assert await svc._check_database() is True

    @pytest.mark.anyio
    async def test_check_database_failure(self):
        session = _make_session(db_ok=False)
        svc = HealthService(session)
        assert await svc._check_database() is False


# ── TestHealthConstants ────────────────────────────────────────


class TestHealthConstants:
    def test_healthy(self):
        assert SYSTEM_HEALTHY == "healthy"

    def test_warning(self):
        assert SYSTEM_WARNING == "warning"

    def test_error(self):
        assert SYSTEM_ERROR == "error"


# ── TestSystemHealthAPI ────────────────────────────────────────


class TestSystemHealthAPI:
    """GET /system/health API endpoint."""

    @pytest.mark.anyio
    async def test_system_health_endpoint(self):
        fake_result = {
            "status": "healthy",
            "database": True,
            "crawler": True,
            "scheduler": True,
            "last_crawl": "2026-07-19T08:00:00",
        }

        mock_session = AsyncMock()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.system.get_async_session_factory", return_value=fake_factory):
            with patch("app.api.main._scheduler_instance", None):
                with patch(
                    "app.services.health.service.HealthService.check",
                    new_callable=AsyncMock,
                    return_value=fake_result,
                ):
                    from app.api.system import system_health
                    result = await system_health()

        assert result["status"] == "healthy"
        assert result["database"] is True

    @pytest.mark.anyio
    async def test_system_health_error_returns_500(self):
        fake_factory = MagicMock(side_effect=RuntimeError("db error"))

        with patch("app.api.system.get_async_session_factory", return_value=fake_factory):
            from app.api.system import system_health
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await system_health()
            assert exc_info.value.status_code == 500
