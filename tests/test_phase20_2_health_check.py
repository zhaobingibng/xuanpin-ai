"""Tests for Phase 20 Task 2: System Health Check Service."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.login_session import LoginSession, LoginStatus
from app.services.health_check import HealthCheckService, run_startup_checks


# ── HealthCheckService Tests ───────────────────────────────────


class TestHealthCheckService:
    """Test HealthCheckService."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create HealthCheckService."""
        return HealthCheckService(mock_session)

    # ── Database Check Tests ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_check_database_success(self, service, mock_session):
        """Test successful database check."""
        mock_result = MagicMock()
        # Create an awaitable that returns 1
        async def mock_scalar():
            return 1
        mock_result.scalar = mock_scalar
        mock_session.execute.return_value = mock_result

        result = await service.check_database()

        assert result["ok"] is True
        assert "OK" in result["message"]

    @pytest.mark.asyncio
    async def test_check_database_failure(self, service, mock_session):
        """Test failed database check."""
        mock_session.execute.side_effect = Exception("Connection refused")

        result = await service.check_database()

        assert result["ok"] is False
        assert "error" in result["message"].lower()

    # ── Taobao Login Check Tests ───────────────────────────────

    @pytest.mark.asyncio
    async def test_check_taobao_login_active(self, service, mock_session):
        """Test active Taobao login."""
        mock_session_obj = LoginSession(
            platform="taobao",
            username="test_user",
            status=LoginStatus.ACTIVE.value,
            login_time=datetime.now(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute.return_value = mock_result

        result = await service.check_taobao_login()

        assert result["ok"] is True
        assert result["status"] == "ACTIVE"
        assert result["username"] == "test_user"

    @pytest.mark.asyncio
    async def test_check_taobao_login_expired(self, service, mock_session):
        """Test expired Taobao login."""
        mock_session_obj = LoginSession(
            platform="taobao",
            status=LoginStatus.EXPIRED.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute.return_value = mock_result

        result = await service.check_taobao_login()

        assert result["ok"] is False
        assert result["status"] == "EXPIRED"

    @pytest.mark.asyncio
    async def test_check_taobao_login_not_found(self, service, mock_session):
        """Test Taobao login not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.check_taobao_login()

        assert result["ok"] is False
        assert result["status"] == "NOT_FOUND"

    # ── 1688 Login Check Tests ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_check_alibaba_login_active(self, service, mock_session):
        """Test active 1688 login."""
        mock_session_obj = LoginSession(
            platform="1688",
            username="alibaba_user",
            status=LoginStatus.ACTIVE.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute.return_value = mock_result

        result = await service.check_alibaba_login()

        assert result["ok"] is True
        assert result["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_check_alibaba_login_not_found(self, service, mock_session):
        """Test 1688 login not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.check_alibaba_login()

        assert result["ok"] is False
        assert result["status"] == "NOT_FOUND"

    # ── Feishu Config Check Tests ──────────────────────────────

    def test_check_feishu_config_enabled(self, service, tmp_path):
        """Test enabled Feishu config."""
        config_file = tmp_path / "feishu.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "webhook_url": "https://example.com/webhook",
            "secret": "test_secret",
        }))

        result = service.check_feishu_config(str(config_file))

        assert result["ok"] is True
        assert result["enabled"] is True
        assert result["webhook_configured"] is True

    def test_check_feishu_config_enabled_no_webhook(self, service, tmp_path):
        """Test enabled Feishu config without webhook."""
        config_file = tmp_path / "feishu.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "webhook_url": "",
        }))

        result = service.check_feishu_config(str(config_file))

        assert result["ok"] is False
        assert "webhook_url not configured" in result["message"]

    def test_check_feishu_config_disabled(self, service, tmp_path):
        """Test disabled Feishu config."""
        config_file = tmp_path / "feishu.json"
        config_file.write_text(json.dumps({
            "enabled": False,
        }))

        result = service.check_feishu_config(str(config_file))

        assert result["ok"] is True  # Disabled is OK (optional)
        assert result["enabled"] is False

    def test_check_feishu_config_missing(self, service, tmp_path):
        """Test missing Feishu config file."""
        result = service.check_feishu_config(str(tmp_path / "nonexistent.json"))

        assert result["ok"] is False
        assert "not found" in result["message"].lower()

    # ── Run All Checks Tests ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_run_all_checks_healthy(self, service, mock_session, tmp_path):
        """Test all checks passing."""
        # Mock database - create awaitable
        mock_result = MagicMock()
        async def mock_scalar():
            return 1
        mock_result.scalar = mock_scalar
        mock_session.execute.return_value = mock_result

        # Create valid configs
        feishu_config = tmp_path / "feishu.json"
        feishu_config.write_text(json.dumps({"enabled": False}))

        # Mock login sessions
        mock_login = MagicMock()
        mock_login.is_active = True
        mock_login.status = "ACTIVE"
        mock_login.username = "test"
        mock_login.login_time = datetime.now()
        mock_result.scalar_one_or_none.return_value = mock_login

        report = await service.run_all_checks()

        assert report["is_healthy"] is True
        assert "checks" in report
        assert "summary" in report

    @pytest.mark.asyncio
    async def test_run_all_checks_unhealthy(self, service, mock_session):
        """Test unhealthy system."""
        # Mock database failure
        mock_session.execute.side_effect = Exception("DB error")

        report = await service.run_all_checks()

        assert report["is_healthy"] is False

    # ── Report Format Tests ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_format_report(self, service, mock_session):
        """Test report formatting."""
        # Run checks first
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await service.run_all_checks()

        report = service.format_report()

        assert "系统健康报告" in report
        assert "数据库连接" in report
        assert "淘宝登录" in report
        assert "1688登录" in report
        assert "飞书配置" in report

    @pytest.mark.asyncio
    async def test_is_healthy_property(self, service, mock_session):
        """Test is_healthy property."""
        # Initially healthy (no checks run)
        assert service.is_healthy is True

        # After database failure
        mock_session.execute.side_effect = Exception("DB error")
        await service.check_database()

        assert service.is_healthy is False


# ── Startup Checks Tests ───────────────────────────────────────


class TestStartupChecks:
    """Test run_startup_checks function."""

    @pytest.mark.asyncio
    async def test_run_startup_checks(self):
        """Test startup checks entry point."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        report = await run_startup_checks(mock_session)

        assert "is_healthy" in report
        assert "checks" in report
        assert "summary" in report
