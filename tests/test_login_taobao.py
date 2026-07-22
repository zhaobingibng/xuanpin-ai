"""Tests for Phase 42.2 — Taobao login recovery script.

Covers:
- _extract_username from storage_state cookies
- _save_state_files writes to correct paths
- CLI argument parsing (--force, --check-only)
- Login flow with mocked browser (check_login → save → verify)
- Edge cases: empty state, missing cookies, URL-encoded usernames
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the script can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.login_taobao import (
    TAOBAO_STATE_PATH,
    TAOBAO_STORAGE_STATE_PATH,
    _extract_username,
    _save_state_files,
    parse_args,
    main,
)


# ============================================================
# _extract_username
# ============================================================


class TestExtractUsername:
    """Test username extraction from storage_state cookies."""

    def test_extract_from_nk_cookie(self):
        state = {"cookies": [{"name": "_nk_", "value": "testuser123"}]}
        assert _extract_username(state) == "testuser123"

    def test_extract_from_snk_cookie(self):
        state = {"cookies": [{"name": "snk", "value": "shop_owner"}]}
        assert _extract_username(state) == "shop_owner"

    def test_extract_from_nick_cookie(self):
        state = {"cookies": [{"name": "nick", "value": "my_nickname"}]}
        assert _extract_username(state) == "my_nickname"

    def test_extract_from_login_current_pk(self):
        state = {"cookies": [{"name": "login_current_pk", "value": "user@taobao"}]}
        assert _extract_username(state) == "user@taobao"

    def test_url_encoded_username(self):
        """URL-encoded usernames should be decoded."""
        state = {"cookies": [{"name": "_nk_", "value": "%E6%B5%8B%E8%AF%95%E7%94%A8%E6%88%B7"}]}
        result = _extract_username(state)
        assert result is not None
        # Should be decoded to Chinese
        assert "测试用户" in result or "%E6" not in result

    def test_ignores_login_text(self):
        """Values '登录' or '亲，请登录' should be treated as not-logged-in."""
        state = {"cookies": [{"name": "_nk_", "value": "登录"}]}
        assert _extract_username(state) is None

    def test_ignores_qinqing_login(self):
        state = {"cookies": [{"name": "_nk_", "value": "亲，请登录"}]}
        assert _extract_username(state) is None

    def test_empty_state(self):
        assert _extract_username({}) is None

    def test_no_cookies_key(self):
        assert _extract_username({"origins": []}) is None

    def test_empty_cookies(self):
        assert _extract_username({"cookies": []}) is None

    def test_no_matching_cookie_name(self):
        state = {"cookies": [{"name": "other_cookie", "value": "some_value"}]}
        assert _extract_username(state) is None

    def test_prefers_first_match(self):
        """First matching cookie should be used."""
        state = {
            "cookies": [
                {"name": "_nk_", "value": "first_user"},
                {"name": "snk", "value": "second_user"},
            ]
        }
        assert _extract_username(state) == "first_user"


# ============================================================
# _save_state_files
# ============================================================


class TestSaveStateFiles:
    """Test state file saving to correct paths."""

    def test_saves_to_both_paths(self, tmp_path):
        """Both taobao_state.json and taobao_storage_state.json should be created."""
        state = {"cookies": [{"name": "_nk_", "value": "testuser"}]}

        with (
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "taobao_storage_state.json"),
        ):
            _save_state_files(state)

        main_path = tmp_path / "taobao_state.json"
        fallback_path = tmp_path / "taobao_storage_state.json"

        assert main_path.exists()
        assert fallback_path.exists()

        main_data = json.loads(main_path.read_text(encoding="utf-8"))
        assert main_data == state

    def test_creates_parent_dirs(self, tmp_path):
        """Parent directories should be created automatically."""
        state = {"cookies": []}
        deep_path = tmp_path / "deep" / "nested" / "taobao_state.json"

        with patch("scripts.login_taobao.TAOBAO_STATE_PATH", deep_path):
            with patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "other.json"):
                _save_state_files(state)

        assert deep_path.exists()

    def test_json_format_is_correct(self, tmp_path):
        """Saved JSON should be properly formatted with indent=2."""
        state = {"cookies": [{"name": "test", "value": "x"}]}

        with (
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "other.json"),
        ):
            _save_state_files(state)

        content = (tmp_path / "taobao_state.json").read_text(encoding="utf-8")
        # Ensure it's pretty-printed (has newlines and indentation)
        assert "\n" in content
        assert "  " in content

    def test_utf8_encoding(self, tmp_path):
        """State with Chinese characters should be saved correctly."""
        state = {"cookies": [{"name": "_nk_", "value": "测试用户"}]}

        with (
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "other.json"),
        ):
            _save_state_files(state)

        data = json.loads((tmp_path / "taobao_state.json").read_text(encoding="utf-8"))
        assert data["cookies"][0]["value"] == "测试用户"


# ============================================================
# parse_args
# ============================================================


class TestParseArgs:
    """Test CLI argument parsing."""

    def test_default_args(self):
        with patch("sys.argv", ["login_taobao.py"]):
            args = parse_args()
        assert args.force is False
        assert args.check_only is False

    def test_force_flag(self):
        with patch("sys.argv", ["login_taobao.py", "--force"]):
            args = parse_args()
        assert args.force is True

    def test_check_only_flag(self):
        with patch("sys.argv", ["login_taobao.py", "--check-only"]):
            args = parse_args()
        assert args.check_only is True

    def test_both_flags(self):
        with patch("sys.argv", ["login_taobao.py", "--force", "--check-only"]):
            args = parse_args()
        assert args.force is True
        assert args.check_only is True


# ============================================================
# main() — check-only mode
# ============================================================


class TestMainCheckOnly:
    """Test main() in --check-only mode."""

    @pytest.mark.asyncio
    async def test_check_only_logged_in(self, tmp_path):
        """--check-only with valid login returns 0."""
        from app.crawler.taobao import TaobaoCrawler

        with (
            patch("sys.argv", ["login_taobao.py", "--check-only"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl,
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
        ):
            # Mock check_login to return True
            mock_cl.return_value = True

            # Also mock auth_manager to return a state with username
            with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                mock_auth.load_storage_state_data.return_value = {
                    "cookies": [{"name": "_nk_", "value": "testuser"}]
                }

                result = await main()

        assert result == 0

    @pytest.mark.asyncio
    async def test_check_only_not_logged_in(self, tmp_path):
        """--check-only with expired login returns 1."""
        from app.crawler.taobao import TaobaoCrawler

        with (
            patch("sys.argv", ["login_taobao.py", "--check-only"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl,
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
        ):
            mock_cl.return_value = False

            with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                mock_auth.load_storage_state_data.return_value = None

                result = await main()

        assert result == 1


# ============================================================
# main() — force mode (login flow)
# ============================================================


class TestMainForceLogin:
    """Test main() with --force flag."""

    @pytest.mark.asyncio
    async def test_force_login_saves_state(self, tmp_path):
        """--force should trigger login and save state files."""
        from app.crawler.taobao import TaobaoCrawler

        mock_state = {
            "cookies": [
                {"name": "_nk_", "value": "force_login_user"},
                {"name": "token", "value": "abc123"},
            ],
            "origins": [],
        }

        with (
            patch("sys.argv", ["login_taobao.py", "--force"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "storage_state.json"),
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
            patch("scripts.login_taobao.input", return_value=""),  # Skip Enter prompt
        ):
            # Mock crawler methods
            with patch.object(TaobaoCrawler, "_new_context") as mock_ctx:
                mock_page = AsyncMock()
                mock_page.goto = AsyncMock()
                mock_page.wait_for_timeout = AsyncMock()
                mock_page.close = AsyncMock()

                mock_context = AsyncMock()
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.storage_state = AsyncMock(return_value=mock_state)
                mock_context.close = AsyncMock()
                mock_ctx.return_value = mock_context

                with patch.object(TaobaoCrawler, "save_cookies", new_callable=AsyncMock):
                    with patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl:
                        mock_cl.return_value = True

                        with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                            mock_auth.load_storage_state_data.return_value = mock_state

                            result = await main()

            # Verify state file was saved
            assert (tmp_path / "taobao_state.json").exists()

            saved_state = json.loads((tmp_path / "taobao_state.json").read_text(encoding="utf-8"))
            assert saved_state["cookies"][0]["name"] == "_nk_"
            assert saved_state["cookies"][0]["value"] == "force_login_user"

            # check_login should have been called (for verification)
            mock_cl.assert_called()

    @pytest.mark.asyncio
    async def test_force_login_verification_fails(self, tmp_path):
        """If verification fails after login, state still saved, return 2."""
        from app.crawler.taobao import TaobaoCrawler

        mock_state = {"cookies": [{"name": "_nk_", "value": "some_user"}]}

        with (
            patch("sys.argv", ["login_taobao.py", "--force"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "storage_state.json"),
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
            patch("scripts.login_taobao.input", return_value=""),
        ):
            with patch.object(TaobaoCrawler, "_new_context") as mock_ctx:
                mock_page = AsyncMock()
                mock_page.goto = AsyncMock()
                mock_page.wait_for_timeout = AsyncMock()
                mock_page.close = AsyncMock()

                mock_context = AsyncMock()
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.storage_state = AsyncMock(return_value=mock_state)
                mock_context.close = AsyncMock()
                mock_ctx.return_value = mock_context

                with patch.object(TaobaoCrawler, "save_cookies", new_callable=AsyncMock):
                    with patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl:
                        mock_cl.return_value = False

                        with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                            mock_auth.load_storage_state_data.return_value = mock_state

                            result = await main()

            # State still saved even if verification fails
            assert (tmp_path / "taobao_state.json").exists()
            assert result == 2


# ============================================================
# main() — already logged in (no force)
# ============================================================


class TestMainAlreadyLoggedIn:
    """Test main() when user is already logged in."""

    @pytest.mark.asyncio
    async def test_already_logged_in_returns_0(self, tmp_path):
        """If already logged in and no --force, return 0 without re-login."""
        from app.crawler.taobao import TaobaoCrawler

        # Create a dummy state file so has_state is True
        state_path = tmp_path / "taobao_state.json"
        state_path.write_text('{"cookies":[]}', encoding="utf-8")

        with (
            patch("sys.argv", ["login_taobao.py"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", state_path),
            patch.object(TaobaoCrawler, "has_cookies", return_value=True),
            patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl,
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
        ):
            mock_cl.return_value = True

            with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                mock_auth.load_storage_state_data.return_value = {
                    "cookies": [{"name": "_nk_", "value": "existing_user"}]
                }

                result = await main()

            assert result == 0

    @pytest.mark.asyncio
    async def test_cookies_expired_triggers_login(self, tmp_path):
        """If cookies exist but login check fails, should trigger login."""
        from app.crawler.taobao import TaobaoCrawler

        mock_state = {"cookies": [{"name": "_nk_", "value": "renewed_user"}]}

        with (
            patch("sys.argv", ["login_taobao.py"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "taobao_state.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "storage_state.json"),
            patch.object(TaobaoCrawler, "has_cookies", return_value=True),
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
            patch("scripts.login_taobao.input", return_value=""),
        ):
            with patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl:
                # First call: pre-check fails → triggers login
                # Second call: verification after login → succeeds
                mock_cl.side_effect = [False, True]

                with patch.object(TaobaoCrawler, "_new_context") as mock_ctx:
                    mock_page = AsyncMock()
                    mock_page.goto = AsyncMock()
                    mock_page.wait_for_timeout = AsyncMock()
                    mock_page.close = AsyncMock()

                    mock_context = AsyncMock()
                    mock_context.new_page = AsyncMock(return_value=mock_page)
                    mock_context.storage_state = AsyncMock(return_value=mock_state)
                    mock_context.close = AsyncMock()
                    mock_ctx.return_value = mock_context

                    with patch.object(TaobaoCrawler, "save_cookies", new_callable=AsyncMock):
                        with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                            mock_auth.load_storage_state_data.return_value = mock_state

                            result = await main()

                assert result == 0
                assert (tmp_path / "taobao_state.json").exists()


# ============================================================
# main() — no existing credentials
# ============================================================


class TestMainNoCredentials:
    """Test main() when there are no existing credentials."""

    @pytest.mark.asyncio
    async def test_no_credentials_triggers_login(self, tmp_path):
        """No state, no cookies → should trigger login."""
        from app.crawler.taobao import TaobaoCrawler

        mock_state = {"cookies": [{"name": "_nk_", "value": "new_login_user"}]}

        with (
            patch("sys.argv", ["login_taobao.py"]),
            patch("scripts.login_taobao.TAOBAO_STATE_PATH", tmp_path / "nonexistent.json"),
            patch("scripts.login_taobao.TAOBAO_STORAGE_STATE_PATH", tmp_path / "storage_state.json"),
            patch.object(TaobaoCrawler, "has_cookies", return_value=False),
            patch.object(TaobaoCrawler, "close", new_callable=AsyncMock),
            patch("scripts.login_taobao.input", return_value=""),
        ):
            with patch.object(TaobaoCrawler, "check_login", new_callable=AsyncMock) as mock_cl:
                mock_cl.return_value = True

                with patch.object(TaobaoCrawler, "_new_context") as mock_ctx:
                    mock_page = AsyncMock()
                    mock_page.goto = AsyncMock()
                    mock_page.wait_for_timeout = AsyncMock()
                    mock_page.close = AsyncMock()

                    mock_context = AsyncMock()
                    mock_context.new_page = AsyncMock(return_value=mock_page)
                    mock_context.storage_state = AsyncMock(return_value=mock_state)
                    mock_context.close = AsyncMock()
                    mock_ctx.return_value = mock_context

                    with patch.object(TaobaoCrawler, "save_cookies", new_callable=AsyncMock):
                        with patch.object(TaobaoCrawler, "auth_manager") as mock_auth:
                            mock_auth.load_storage_state_data.return_value = mock_state

                            result = await main()

                assert result == 0
                assert mock_ctx.called  # Login was triggered


# ============================================================
# State file path correctness
# ============================================================


class TestStateFilePaths:
    """Verify that state file path constants are correct."""

    def test_taobao_state_path_ends_with_storage(self):
        path_str = str(TAOBAO_STATE_PATH)
        assert "storage" in path_str
        assert path_str.endswith("taobao_state.json")

    def test_storage_state_path_ends_with_cookies(self):
        path_str = str(TAOBAO_STORAGE_STATE_PATH)
        assert "cookies" in path_str
        assert "taobao_storage_state.json" in path_str

    def test_paths_are_absolute(self):
        assert TAOBAO_STATE_PATH.is_absolute()
        assert TAOBAO_STORAGE_STATE_PATH.is_absolute()
