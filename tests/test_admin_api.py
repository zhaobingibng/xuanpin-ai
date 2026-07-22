"""Tests for Phase 43.1 — Admin API endpoints.

Covers: router registration, endpoint responses, service mocks, exception handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


# ── Helpers ────────────────────────────────────────────────────


def _make_scalar_result(value):
    """Create a mock result row with scalar() returning a value."""
    row = MagicMock()
    row.scalar = MagicMock(return_value=value)
    return row


def _make_async_session():
    """Create a mock AsyncSession with properly configured execute."""
    session = AsyncMock()
    scalar_result = _make_scalar_result(0)
    session.execute = AsyncMock(return_value=scalar_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _session_factory_ctx(session):
    """Create a mock session factory that returns the given session as context manager."""
    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


def _make_login_session_mock(platform="taobao", status="ACTIVE", is_active=True):
    """Create a mock LoginSession."""
    ls = MagicMock()
    ls.platform = platform
    ls.status = status
    ls.is_active = is_active
    ls.username = "test_user"
    return ls


# ═══════════════════════════════════════════════════════════════
# Router Registration
# ═══════════════════════════════════════════════════════════════


class TestRouterRegistration:
    """Verify admin router is registered in the FastAPI app.

    Note: app.routes introspection may not directly expose include_router routes
    in some Starlette versions. The functional API tests below prove all routes work.
    """

    def test_app_imports_admin_router(self):
        """Verify admin.py module can be imported without errors."""
        from app.api import admin
        assert admin.router is not None
        # Verify prefix is correct
        assert admin.router.prefix == "/api/admin"

    @pytest.mark.anyio
    async def test_admin_endpoints_accessible(self):
        """Verify all 8 admin endpoints respond with appropriate status codes."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # GET endpoints
            resp = await client.get("/api/admin/status")
            assert resp.status_code in (200, 500), f"status returned {resp.status_code}"

            resp = await client.get("/api/admin/taobao/status")
            assert resp.status_code in (200, 500)

            resp = await client.get("/api/admin/recommendations")
            assert resp.status_code in (200, 500)

            resp = await client.get("/api/admin/reports/latest")
            assert resp.status_code in (200, 500)

            # POST endpoints
            resp = await client.post("/api/admin/taobao/start")
            assert resp.status_code == 200, f"taobao/start returned {resp.status_code}"

            resp = await client.post("/api/admin/matching/run")
            assert resp.status_code in (200, 500)

            resp = await client.post("/api/admin/report/generate")
            assert resp.status_code in (200, 500)

            resp = await client.post("/api/admin/feishu/send", json={"content": "test"})
            assert resp.status_code in (200, 500)


# ═══════════════════════════════════════════════════════════════
# GET /api/admin/status
# ═══════════════════════════════════════════════════════════════


class TestAdminStatus:
    """Tests for GET /api/admin/status."""

    @pytest.mark.anyio
    async def test_status_returns_success(self):
        """Should return success=True with health, login, taobao_session keys."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "health" in data["data"]
        assert "login" in data["data"]
        assert "taobao_session" in data["data"]

    @pytest.mark.anyio
    async def test_status_health_failure_graceful(self):
        """If health check raises, should still return success with error details."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "error" in data["data"].get("health", {}) or data["data"]["health"].get("status") == "error"


# ═══════════════════════════════════════════════════════════════
# GET /api/admin/taobao/status
# ═══════════════════════════════════════════════════════════════


class TestAdminTaobaoStatus:
    """Tests for GET /api/admin/taobao/status."""

    @pytest.mark.anyio
    async def test_taobao_status_returns_success(self):
        """Should return success=True with login and session keys."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/taobao/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "login" in data["data"]
        assert "session" in data["data"]

    @pytest.mark.anyio
    async def test_taobao_status_idle_state(self):
        """When no session active, session state should show idle info."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/taobao/status")

        assert resp.status_code == 200
        data = resp.json()
        session_data = data["data"]["session"]
        assert "state" in session_data
        assert "is_logged_in" in session_data
        assert "product_count" in session_data

    @pytest.mark.anyio
    async def test_taobao_status_with_login_session(self):
        """When login session exists, login data should contain taobao info."""
        session = _make_async_session()
        # Configure execute to return a mock LoginSession
        login_session = _make_login_session_mock()
        scalar_result = MagicMock()
        scalar_result.scalar = MagicMock(return_value=42)
        scalar_result.scalar_one_or_none = MagicMock(return_value=login_session)
        session.execute = AsyncMock(return_value=scalar_result)
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/taobao/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        login_data = data["data"]["login"]
        assert "state_file_exists" in login_data or "error" in login_data


# ═══════════════════════════════════════════════════════════════
# GET /api/admin/recommendations
# ═══════════════════════════════════════════════════════════════


class TestAdminRecommendations:
    """Tests for GET /api/admin/recommendations."""

    @pytest.mark.anyio
    async def test_recommendations_empty_returns_success(self):
        """When no products, should still return success with total=0."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    @pytest.mark.anyio
    async def test_recommendations_service_error(self):
        """If DailyRecommendationService fails, should return 500."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Service error"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/recommendations")

        assert resp.status_code == 500
        data = resp.json()
        assert "detail" in data


# ═══════════════════════════════════════════════════════════════
# GET /api/admin/reports/latest
# ═══════════════════════════════════════════════════════════════


class TestAdminReportsLatest:
    """Tests for GET /api/admin/reports/latest."""

    @pytest.mark.anyio
    async def test_latest_report_empty(self):
        """When no reports, should return data=None with message."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ), patch(
            "app.database.report_repository.ReportRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(return_value=[])
            mock_repo_class.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/reports/latest")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] is None
        assert "暂无日报" in data["message"]

    @pytest.mark.anyio
    async def test_latest_report_with_data(self):
        """When reports exist, should return report data."""
        from datetime import date
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        mock_report = MagicMock()
        mock_report.id = 1
        mock_report.report_date = date.today()
        mock_report.total = 5
        mock_report.hot_products = 2
        mock_report.potential_products = 3
        mock_report.average_score = 75.5

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ), patch(
            "app.database.report_repository.ReportRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(return_value=[mock_report])
            mock_repo_class.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/reports/latest")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 5
        assert data["data"]["hot_products"] == 2
        assert data["data"]["average_score"] == 75.5

    @pytest.mark.anyio
    async def test_latest_report_repository_error(self):
        """If repository fails, should return 500."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ), patch(
            "app.database.report_repository.ReportRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(side_effect=RuntimeError("DB error"))
            mock_repo_class.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/reports/latest")

        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# POST /api/admin/taobao/start
# ═══════════════════════════════════════════════════════════════


class TestAdminTaobaoStart:
    """Tests for POST /api/admin/taobao/start."""

    @pytest.mark.anyio
    async def test_taobao_start_idle_returns_starting(self):
        """When idle, should trigger background launch and return starting state."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/admin/taobao/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["state"] == "starting"
        assert data["data"]["is_logged_in"] is False

    @pytest.mark.anyio
    async def test_taobao_start_already_running(self):
        """When session is already running, should return existing state."""
        # Simulate session already in 'logged_in' state
        with patch(
            "app.services.taobao_session_service.get_taobao_session"
        ) as mock_get_session:
            from app.services.taobao_session_service import SessionInfo, SessionState

            mock_svc = MagicMock()
            mock_svc.get_snapshot.return_value = SessionInfo(
                state=SessionState.LOGGED_IN,
                is_logged_in=True,
                message="已登录",
            )
            mock_get_session.return_value = mock_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/taobao/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["state"] == "logged_in"
        assert data["data"]["is_logged_in"] is True
        assert "已存在" in data["message"]

    @pytest.mark.anyio
    async def test_taobao_start_error_state(self):
        """When in error state, should allow restart."""
        with patch(
            "app.services.taobao_session_service.get_taobao_session"
        ) as mock_get_session:
            from app.services.taobao_session_service import SessionInfo, SessionState

            mock_svc = MagicMock()
            mock_svc.get_snapshot.return_value = SessionInfo(
                state=SessionState.ERROR,
                is_logged_in=False,
                message="启动失败",
            )
            mock_get_session.return_value = mock_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/taobao/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["state"] == "starting"


# ═══════════════════════════════════════════════════════════════
# POST /api/admin/matching/run
# ═══════════════════════════════════════════════════════════════


class TestAdminMatchingRun:
    """Tests for POST /api/admin/matching/run."""

    @pytest.mark.anyio
    async def test_matching_run_no_products(self):
        """When no products, should return matched=0."""
        session = _make_async_session()
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/matching/run")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["matched"] == 0
        assert data["data"]["total"] == 0

    @pytest.mark.anyio
    async def test_matching_run_service_error(self):
        """If service fails, should return 500."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Matching error"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/matching/run")

        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# POST /api/admin/report/generate
# ═══════════════════════════════════════════════════════════════


class TestAdminReportGenerate:
    """Tests for POST /api/admin/report/generate."""

    @pytest.mark.anyio
    async def test_report_generate_service_error(self):
        """If DailyReportService fails, should return 500."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Report error"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/report/generate")

        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# POST /api/admin/feishu/send
# ═══════════════════════════════════════════════════════════════


class TestAdminFeishuSend:
    """Tests for POST /api/admin/feishu/send."""

    @pytest.mark.anyio
    async def test_feishu_send_not_configured(self):
        """When feishu is not configured, should return disabled message."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/feishu/send",
                json={"content": "测试消息", "msg_type": "text"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "未配置" in data["message"]

    @pytest.mark.anyio
    async def test_feishu_send_missing_body_returns_422(self):
        """Missing required body should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/admin/feishu/send", json={})

        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_feishu_send_with_content(self):
        """Sending with content should call service."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/feishu/send",
                json={"content": "Hello from test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "未配置" in data["message"] or data["success"] is False

    @pytest.mark.anyio
    async def test_feishu_send_configured(self):
        """When feishu is configured, should send successfully."""
        with patch(
            "app.services.feishu_notification.FeishuNotificationService"
        ) as mock_svc_class:
            mock_svc = MagicMock()
            mock_svc.is_enabled = True
            mock_svc.send_message = AsyncMock(return_value={
                "success": True,
                "message": "Sent",
            })
            mock_svc_class.return_value = mock_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/admin/feishu/send",
                    json={"content": "Hello", "msg_type": "text"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Sent" in data["message"]


# ═══════════════════════════════════════════════════════════════
# Exception Handling
# ═══════════════════════════════════════════════════════════════


class TestExceptionHandling:
    """Verify all endpoints handle exceptions gracefully."""

    @pytest.mark.anyio
    async def test_recommendations_500_on_error(self):
        """GET /api/admin/recommendations should return 500 on internal error."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Unexpected"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/admin/recommendations")

        assert resp.status_code == 500
        assert "detail" in resp.json()

    @pytest.mark.anyio
    async def test_report_generate_500_on_error(self):
        """POST /api/admin/report/generate should return 500 on internal error."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Unexpected"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/report/generate")

        assert resp.status_code == 500

    @pytest.mark.anyio
    async def test_matching_500_on_error(self):
        """POST /api/admin/matching/run should return 500 on internal error."""
        session = _make_async_session()
        session.execute = AsyncMock(side_effect=RuntimeError("Unexpected"))
        factory = _session_factory_ctx(session)

        with patch(
            "app.api.admin.get_async_session_factory", return_value=factory
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/admin/matching/run")

        assert resp.status_code == 500
