"""Tests for Phase 22 Task 1: Login State Configuration."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.login_session import LoginSession, LoginStatus
from app.services.login_helper import LoginHelper, TAOBAO_STATE_PATH, ALIBABA_STATE_PATH
from app.crawler.auth_manager import AuthManager


# ── LoginHelper Tests ──────────────────────────────────────────


class TestLoginHelper:
    """Test LoginHelper service."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def helper(self, mock_session):
        """Create LoginHelper."""
        return LoginHelper(mock_session)

    # ── State File Path Tests ──────────────────────────────────

    def test_get_state_path_taobao(self, helper):
        """Test state path for taobao."""
        path = helper.get_state_path("taobao")
        assert path == TAOBAO_STATE_PATH

    def test_get_state_path_alibaba(self, helper):
        """Test state path for alibaba."""
        path = helper.get_state_path("1688")
        assert path == ALIBABA_STATE_PATH

    def test_get_state_path_unknown(self, helper):
        """Test state path for unknown platform."""
        path = helper.get_state_path("unknown")
        assert "unknown_state.json" in str(path)

    # ── State File Operations Tests ────────────────────────────

    def test_save_state_file(self, helper, tmp_path):
        """Test saving state file."""
        # Override path for testing
        test_path = tmp_path / "test_state.json"
        helper.get_state_path = lambda p: test_path

        state_data = {"cookies": [{"name": "test", "value": "123"}]}
        result = helper.save_state_file("taobao", state_data)

        assert result is True
        assert test_path.exists()

        with open(test_path, "r") as f:
            saved_data = json.load(f)
        assert saved_data == state_data

    def test_load_state_file(self, helper, tmp_path):
        """Test loading state file."""
        test_path = tmp_path / "test_state.json"
        state_data = {"cookies": [{"name": "test", "value": "123"}]}
        with open(test_path, "w") as f:
            json.dump(state_data, f)

        helper.get_state_path = lambda p: test_path
        loaded_data = helper.load_state_file("taobao")

        assert loaded_data == state_data

    def test_load_state_file_not_found(self, helper, tmp_path):
        """Test loading non-existent state file."""
        test_path = tmp_path / "nonexistent.json"
        helper.get_state_path = lambda p: test_path

        result = helper.load_state_file("taobao")
        assert result is None

    def test_has_state_file(self, helper, tmp_path):
        """Test checking state file existence."""
        test_path = tmp_path / "test_state.json"
        helper.get_state_path = lambda p: test_path

        # Initially doesn't exist
        assert helper.has_state_file("taobao") is False

        # Create file
        with open(test_path, "w") as f:
            json.dump({"test": True}, f)

        assert helper.has_state_file("taobao") is True

    # ── LoginSession Database Tests ────────────────────────────

    @pytest.mark.asyncio
    async def test_update_login_session_create(self, helper, mock_session):
        """Test creating new login session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await helper.update_login_session("taobao", "test_user", LoginStatus.ACTIVE)

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_login_session_update(self, helper, mock_session):
        """Test updating existing login session."""
        existing_session = LoginSession(
            platform="taobao",
            username="old_user",
            status=LoginStatus.UNKNOWN.value,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_session
        mock_session.execute.return_value = mock_result

        result = await helper.update_login_session("taobao", "new_user", LoginStatus.ACTIVE)

        assert result is True
        assert existing_session.username == "new_user"
        assert existing_session.status == LoginStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_get_login_session(self, helper, mock_session):
        """Test getting login session."""
        expected_session = LoginSession(
            platform="taobao",
            username="test_user",
            status=LoginStatus.ACTIVE.value,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_session
        mock_session.execute.return_value = mock_result

        session = await helper.get_login_session("taobao")

        assert session == expected_session

    @pytest.mark.asyncio
    async def test_mark_login_success(self, helper, mock_session, tmp_path):
        """Test marking login success."""
        test_path = tmp_path / "test_state.json"
        helper.get_state_path = lambda p: test_path

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        state_data = {"cookies": []}
        result = await helper.mark_login_success("taobao", state_data, "test_user")

        assert result is True
        assert test_path.exists()

    @pytest.mark.asyncio
    async def test_get_login_status_summary(self, helper, mock_session):
        """Test getting login status summary."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        summary = await helper.get_login_status_summary()

        assert "taobao" in summary
        assert "1688" in summary
        assert "state_file_exists" in summary["taobao"]
        assert "db_status" in summary["taobao"]


# ── AuthManager Tests ──────────────────────────────────────────


class TestAuthManager:
    """Test AuthManager with new state file paths."""

    @pytest.fixture
    def auth_manager(self, tmp_path):
        """Create AuthManager with temp cookie dir."""
        return AuthManager(cookie_dir=tmp_path)

    def test_state_file_paths_defined(self):
        """Test that state file paths are defined."""
        assert "taobao" in AuthManager.STATE_FILE_PATHS
        assert "1688" in AuthManager.STATE_FILE_PATHS

    def test_storage_state_path_new_format(self, auth_manager, tmp_path):
        """Test storage_state_path with new format."""
        # Create state file at new path
        new_path = Path("storage/taobao_state.json")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        with open(new_path, "w") as f:
            json.dump({"cookies": []}, f)

        path = auth_manager._storage_state_path("taobao")

        # Should return new path if it exists
        assert path == new_path

        # Cleanup
        new_path.unlink()

    def test_storage_state_path_fallback(self, auth_manager, tmp_path):
        """Test storage_state_path fallback to cookie_dir."""
        # No new state file exists
        path = auth_manager._storage_state_path("taobao")

        # Should fall back to cookie_dir
        assert "taobao_storage_state.json" in str(path)

    @pytest.mark.asyncio
    async def test_check_login_state_with_state_file(self, auth_manager, tmp_path):
        """Test check_login_state with new state file."""
        # Create state file
        new_path = Path("storage/taobao_state.json")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        with open(new_path, "w") as f:
            json.dump({"cookies": [{"name": "_nk_", "value": "test_user"}]}, f)

        state = await auth_manager.check_login_state("taobao")

        # Should find cookies and return UNKNOWN (no live check)
        assert state.platform == "taobao"
        assert state.username == "test_user"

        # Cleanup
        new_path.unlink()


# ── State File Integration Tests ───────────────────────────────


class TestStateFileIntegration:
    """Test state file integration."""

    def test_taobao_state_file_structure(self, tmp_path):
        """Test taobao state file structure."""
        state_data = {
            "cookies": [
                {"name": "_nk_", "value": "test_user", "domain": ".taobao.com"},
                {"name": "cookie2", "value": "value2", "domain": ".taobao.com"},
            ],
            "origins": [],
        }

        state_path = tmp_path / "taobao_state.json"
        with open(state_path, "w") as f:
            json.dump(state_data, f)

        # Verify structure
        with open(state_path, "r") as f:
            loaded = json.load(f)

        assert "cookies" in loaded
        assert len(loaded["cookies"]) == 2

    def test_alibaba_state_file_structure(self, tmp_path):
        """Test alibaba state file structure."""
        state_data = {
            "cookies": [
                {"name": "cna", "value": "test_cna", "domain": ".1688.com"},
            ],
            "origins": [],
        }

        state_path = tmp_path / "alibaba_state.json"
        with open(state_path, "w") as f:
            json.dump(state_data, f)

        # Verify structure
        with open(state_path, "r") as f:
            loaded = json.load(f)

        assert "cookies" in loaded
        assert len(loaded["cookies"]) == 1
