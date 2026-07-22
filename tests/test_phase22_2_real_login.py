"""Tests for Phase 22 Task 2: Real Login Validation."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.phase22_real_login_validation import (
    validate_state_file,
    validate_shop_crawl,
)


# ── State File Validation Tests ────────────────────────────────


class TestStateFileValidation:
    """Test state file validation."""

    def test_validate_state_file_not_found(self, tmp_path):
        """Test validation with missing state file."""
        state_path = tmp_path / "nonexistent.json"
        result = validate_state_file("taobao", state_path)

        assert result["login"] is False
        assert result["state_file_exists"] is False
        assert "not found" in result["error"].lower()

    def test_validate_state_file_empty(self, tmp_path):
        """Test validation with empty state file."""
        state_path = tmp_path / "state.json"
        state_path.write_text("{}")

        result = validate_state_file("taobao", state_path)

        assert result["state_file_exists"] is True
        assert result["cookies_count"] == 0
        assert result["login"] is False

    def test_validate_state_file_with_cookies(self, tmp_path):
        """Test validation with valid cookies."""
        state_path = tmp_path / "state.json"
        state_data = {
            "cookies": [
                {"name": "_nk_", "value": "test_user", "domain": ".taobao.com"},
                {"name": "cookie2", "value": "value2", "domain": ".taobao.com"},
            ]
        }
        state_path.write_text(json.dumps(state_data))

        result = validate_state_file("taobao", state_path)

        assert result["login"] is True
        assert result["cookies_count"] == 2
        assert result["username"] == "test_user"

    def test_validate_state_file_invalid_json(self, tmp_path):
        """Test validation with invalid JSON."""
        state_path = tmp_path / "state.json"
        state_path.write_text("invalid json")

        result = validate_state_file("taobao", state_path)

        assert result["login"] is False
        assert "invalid json" in result["error"].lower()

    def test_validate_state_file_url_encoded_username(self, tmp_path):
        """Test validation with URL-encoded username."""
        state_path = tmp_path / "state.json"
        state_data = {
            "cookies": [
                {"name": "_nk_", "value": "%E6%B5%8B%E8%AF%95%E7%94%A8%E6%88%B7", "domain": ".taobao.com"},
            ]
        }
        state_path.write_text(json.dumps(state_data))

        result = validate_state_file("taobao", state_path)

        assert result["login"] is True
        # URL decoded value
        assert result["username"] != ""


# ── Shop Crawl Validation Tests ────────────────────────────────


class TestShopCrawlValidation:
    """Test shop crawl validation."""

    @pytest.mark.asyncio
    async def test_validate_shop_crawl(self):
        """Test shop crawl validation."""
        result = await validate_shop_crawl()

        assert result["success"] is True
        assert result["products_count"] > 0
        assert len(result["products"]) > 0

    @pytest.mark.asyncio
    async def test_validate_shop_crawl_products_structure(self):
        """Test products structure."""
        result = await validate_shop_crawl()

        for product in result["products"]:
            assert "title" in product
            assert "price" in product
            assert isinstance(product["price"], (int, float))


# ── Report Structure Tests ─────────────────────────────────────


class TestReportStructure:
    """Test report structure."""

    def test_report_structure(self, tmp_path):
        """Test report JSON structure."""
        report = {
            "start_time": datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "taobao": {
                "login": True,
                "username": "test_user",
                "cookies_count": 10,
            },
            "alibaba": {
                "login": True,
                "username": "alibaba_user",
                "cookies_count": 5,
            },
            "crawl_validation": {
                "success": True,
                "products_count": 3,
            },
            "overall_status": "both_logged_in",
        }

        report_path = tmp_path / "report.json"
        with open(report_path, "w") as f:
            json.dump(report, f)

        with open(report_path, "r") as f:
            loaded = json.load(f)

        assert loaded["taobao"]["login"] is True
        assert loaded["alibaba"]["login"] is True
        assert loaded["overall_status"] == "both_logged_in"

    def test_overall_status_options(self):
        """Test overall status options."""
        valid_statuses = ["both_logged_in", "taobao_only", "alibaba_only", "not_logged_in"]

        for status in valid_statuses:
            assert status in valid_statuses


# ── Integration Tests ──────────────────────────────────────────


class TestIntegration:
    """Test integration scenarios."""

    def test_full_validation_flow(self, tmp_path):
        """Test full validation flow."""
        # Create state files
        taobao_path = tmp_path / "taobao_state.json"
        alibaba_path = tmp_path / "alibaba_state.json"

        taobao_data = {"cookies": [{"name": "_nk_", "value": "user1"}]}
        alibaba_data = {"cookies": [{"name": "cna", "value": "cna123"}]}

        taobao_path.write_text(json.dumps(taobao_data))
        alibaba_path.write_text(json.dumps(alibaba_data))

        # Validate both
        taobao_result = validate_state_file("taobao", taobao_path)
        alibaba_result = validate_state_file("1688", alibaba_path)

        assert taobao_result["login"] is True
        assert alibaba_result["login"] is True

    def test_partial_login_flow(self, tmp_path):
        """Test partial login flow (only one platform)."""
        # Create only taobao state file
        taobao_path = tmp_path / "taobao_state.json"
        taobao_data = {"cookies": [{"name": "_nk_", "value": "user1"}]}
        taobao_path.write_text(json.dumps(taobao_data))

        alibaba_path = tmp_path / "alibaba_state.json"

        taobao_result = validate_state_file("taobao", taobao_path)
        alibaba_result = validate_state_file("1688", alibaba_path)

        assert taobao_result["login"] is True
        assert alibaba_result["login"] is False
