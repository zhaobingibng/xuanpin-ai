"""Tests for Phase 16.9 Task 1: AuthManager and LoginSession."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.auth_manager import AuthManager, AuthState, LoginStatus
from app.models.login_session import LoginSession, LoginStatus as ModelLoginStatus


# ── LoginSession Model Tests ─────────────────────────────────


class TestLoginSession:
    """Test LoginSession ORM model."""

    def test_create_session(self):
        """Test creating a login session."""
        session = LoginSession(
            platform="taobao",
            username="test_user",
            status=LoginStatus.ACTIVE.value,
        )
        assert session.platform == "taobao"
        assert session.username == "test_user"
        assert session.status == "ACTIVE"

    def test_is_active(self):
        """Test is_active property."""
        session = LoginSession(platform="taobao", status=LoginStatus.ACTIVE.value)
        assert session.is_active is True
        assert session.is_expired is False

    def test_is_expired(self):
        """Test is_expired property."""
        session = LoginSession(platform="taobao", status=LoginStatus.EXPIRED.value)
        assert session.is_active is False
        assert session.is_expired is True

    def test_mark_active(self):
        """Test mark_active method."""
        session = LoginSession(platform="taobao", status=LoginStatus.UNKNOWN.value)
        session.mark_active(username="new_user")
        assert session.status == "ACTIVE"
        assert session.username == "new_user"

    def test_mark_expired(self):
        """Test mark_expired method."""
        session = LoginSession(platform="taobao", status=LoginStatus.ACTIVE.value)
        session.mark_expired()
        assert session.status == "EXPIRED"

    def test_mark_unknown(self):
        """Test mark_unknown method."""
        session = LoginSession(platform="taobao", status=LoginStatus.ACTIVE.value)
        session.mark_unknown()
        assert session.status == "UNKNOWN"

    def test_repr(self):
        """Test __repr__."""
        session = LoginSession(
            id=1,
            platform="taobao",
            username="test_user",
            status=LoginStatus.ACTIVE.value,
        )
        repr_str = repr(session)
        assert "LoginSession" in repr_str
        assert "taobao" in repr_str
        assert "test_user" in repr_str


# ── AuthState Tests ──────────────────────────────────────────


class TestAuthState:
    """Test AuthState dataclass."""

    def test_active_state(self):
        """Test active state properties."""
        state = AuthState(
            status=LoginStatus.ACTIVE,
            platform="taobao",
            username="user1",
        )
        assert state.is_active is True
        assert state.is_expired is False
        assert state.is_unknown is False

    def test_expired_state(self):
        """Test expired state properties."""
        state = AuthState(
            status=LoginStatus.EXPIRED,
            platform="taobao",
        )
        assert state.is_active is False
        assert state.is_expired is True
        assert state.is_unknown is False

    def test_unknown_state(self):
        """Test unknown state properties."""
        state = AuthState(
            status=LoginStatus.UNKNOWN,
            platform="taobao",
        )
        assert state.is_active is False
        assert state.is_expired is False
        assert state.is_unknown is True


# ── AuthManager Tests ────────────────────────────────────────


class TestAuthManager:
    """Test AuthManager class."""

    @pytest.fixture
    def auth_manager(self, tmp_path):
        """Create AuthManager with temp directory."""
        return AuthManager(tmp_path)

    def test_has_storage_state_false(self, auth_manager):
        """Test has_storage_state when file doesn't exist."""
        # Use a platform that doesn't have state files
        assert auth_manager.has_storage_state("nonexistent_platform") is False

    def test_has_storage_state_true(self, auth_manager, tmp_path):
        """Test has_storage_state when file exists."""
        storage_file = tmp_path / "taobao_storage_state.json"
        storage_file.write_text('{"cookies": []}')
        assert auth_manager.has_storage_state("taobao") is True

    def test_has_cookies_false(self, auth_manager):
        """Test has_cookies when file doesn't exist."""
        assert auth_manager.has_cookies("taobao") is False

    def test_has_cookies_true(self, auth_manager, tmp_path):
        """Test has_cookies when file exists."""
        cookie_file = tmp_path / "taobao.json"
        cookie_file.write_text('[{"name": "cookie1"}]')
        assert auth_manager.has_cookies("taobao") is True

    def test_load_storage_state_data_not_found(self, auth_manager):
        """Test load_storage_state_data when file not found."""
        # Use a platform that doesn't have state files
        result = auth_manager.load_storage_state_data("nonexistent_platform")
        assert result is None

    def test_load_storage_state_data_success(self, auth_manager, tmp_path):
        """Test load_storage_state_data with valid file."""
        # Use test_platform to avoid conflict with real state files
        storage_file = tmp_path / "test_platform_storage_state.json"
        data = {"cookies": [{"name": "test", "value": "123"}]}
        storage_file.write_text(json.dumps(data))

        result = auth_manager.load_storage_state_data("test_platform")
        assert result is not None
        assert "cookies" in result
        assert len(result["cookies"]) == 1

    def test_extract_username_from_storage(self, auth_manager, tmp_path):
        """Test extracting username from storage_state cookies."""
        storage_file = tmp_path / "test_platform_storage_state.json"
        data = {
            "cookies": [
                {"name": "_nk_", "value": "%E6%B5%8B%E8%AF%95%E7%94%A8%E6%88%B7"},  # URL encoded
                {"name": "other", "value": "ignored"},
            ]
        }
        storage_file.write_text(json.dumps(data))

        username = auth_manager.extract_username_from_storage("test_platform")
        assert username is not None
        # URL decoded value
        assert "测试用户" in username or "%E6%B5%8B%E8%AF%95" in username

    def test_extract_username_not_found(self, auth_manager, tmp_path):
        """Test extracting username when not in cookies."""
        storage_file = tmp_path / "test_platform_storage_state.json"
        data = {"cookies": [{"name": "other", "value": "no_username"}]}
        storage_file.write_text(json.dumps(data))

        username = auth_manager.extract_username_from_storage("test_platform")
        assert username is None

    async def test_check_login_state_no_cookies(self, auth_manager):
        """Test check_login_state with no cookies."""
        state = await auth_manager.check_login_state("nonexistent_platform")
        assert state.status == LoginStatus.UNKNOWN
        assert state.detail == "no_cookies_or_storage_state"

    async def test_check_login_state_with_cookies_no_browser(self, auth_manager, tmp_path):
        """Test check_login_state with cookies but no browser manager."""
        # Create storage state file
        storage_file = tmp_path / "test_platform_storage_state.json"
        storage_file.write_text('{"cookies": []}')

        state = await auth_manager.check_login_state("test_platform")
        assert state.status == LoginStatus.UNKNOWN
        assert state.detail == "cookies_exist_no_live_check"

    async def test_check_login_state_with_live_check_active(self, auth_manager, tmp_path):
        """Test check_login_state with live check returning active."""
        # Create storage state file
        storage_file = tmp_path / "taobao_storage_state.json"
        storage_file.write_text('{"cookies": []}')

        # Mock browser manager
        mock_browser = MagicMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_element = AsyncMock()
        mock_element.inner_text = AsyncMock(return_value="test_user")
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        state = await auth_manager.check_login_state("taobao", mock_browser)
        assert state.status == LoginStatus.ACTIVE
        assert state.username == "test_user"

    async def test_check_login_state_with_live_check_expired(self, auth_manager, tmp_path):
        """Test check_login_state with live check returning expired."""
        # Create storage state file
        storage_file = tmp_path / "taobao_storage_state.json"
        storage_file.write_text('{"cookies": []}')

        # Mock browser manager - no login element found
        mock_browser = MagicMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        state = await auth_manager.check_login_state("taobao", mock_browser)
        assert state.status == LoginStatus.EXPIRED

    def test_can_crawl_with_cookies(self, auth_manager, tmp_path):
        """Test can_crawl with cookies present."""
        storage_file = tmp_path / "taobao_storage_state.json"
        storage_file.write_text('{"cookies": []}')

        can_crawl, reason = auth_manager.can_crawl("taobao")
        assert can_crawl is True
        assert reason == "cookies_exist"

    def test_can_crawl_without_cookies(self, auth_manager):
        """Test can_crawl without cookies."""
        # Use a platform that doesn't have state files
        can_crawl, reason = auth_manager.can_crawl("nonexistent_platform")
        assert can_crawl is False
        assert reason == "no_login_credentials"


# ── TaobaoCrawler Auth Integration Tests ─────────────────────


class TestTaobaoCrawlerAuth:
    """Test TaobaoCrawler auth integration."""

    @pytest.fixture
    def crawler(self):
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)

            from app.crawler.taobao import TaobaoCrawler
            return TaobaoCrawler()

    def test_auth_manager_property(self, crawler):
        """Test auth_manager lazy property."""
        auth = crawler.auth_manager
        assert isinstance(auth, AuthManager)
        # Same instance on second access
        assert crawler.auth_manager is auth

    async def test_pre_crawl_auth_check(self, crawler):
        """Test pre_crawl_auth_check method."""
        # Mock auth_manager.check_login_state
        mock_state = AuthState(
            status=LoginStatus.ACTIVE,
            platform="taobao",
            username="test_user",
        )
        crawler.auth_manager.check_login_state = AsyncMock(return_value=mock_state)

        state = await crawler.pre_crawl_auth_check()
        assert state.is_active is True
        assert state.username == "test_user"


# ── LoginStatus Enum Tests ───────────────────────────────────


class TestLoginStatusEnum:
    """Test LoginStatus enum consistency."""

    def test_auth_manager_status_values(self):
        """Test AuthManager LoginStatus values."""
        assert LoginStatus.ACTIVE.value == "ACTIVE"
        assert LoginStatus.EXPIRED.value == "EXPIRED"
        assert LoginStatus.UNKNOWN.value == "UNKNOWN"

    def test_model_status_values(self):
        """Test Model LoginStatus values."""
        assert ModelLoginStatus.ACTIVE.value == "ACTIVE"
        assert ModelLoginStatus.EXPIRED.value == "EXPIRED"
        assert ModelLoginStatus.UNKNOWN.value == "UNKNOWN"

    def test_status_values_match(self):
        """Test that AuthManager and Model status values match."""
        assert LoginStatus.ACTIVE.value == ModelLoginStatus.ACTIVE.value
        assert LoginStatus.EXPIRED.value == ModelLoginStatus.EXPIRED.value
        assert LoginStatus.UNKNOWN.value == ModelLoginStatus.UNKNOWN.value
