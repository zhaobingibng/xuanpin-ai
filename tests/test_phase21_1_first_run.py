"""Tests for Phase 21 Task 1: First Production Run Validation."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.health_check import HealthCheckService
from app.tasks.daily_selection_task import run_daily_selection


# ── Validation Flow Tests ──────────────────────────────────────


class TestFirstRunValidation:
    """Test first production run validation flow."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        # Mock query results
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        return session

    @pytest.mark.asyncio
    async def test_health_check_integration(self, mock_session):
        """Test health check integration."""
        service = HealthCheckService(mock_session)
        report = await service.run_all_checks()

        assert "is_healthy" in report
        assert "checks" in report
        assert "database" in report["checks"]

    @pytest.mark.asyncio
    async def test_daily_selection_integration(self, mock_session):
        """Test daily selection task integration."""
        result = await run_daily_selection(mock_session)

        assert "success" in result
        assert "products_count" in result
        assert "new_products_count" in result
        assert "matched_count" in result

    @pytest.mark.asyncio
    async def test_full_validation_flow(self, mock_session):
        """Test complete validation flow."""
        # Step 1: Health check
        health_service = HealthCheckService(mock_session)
        health_report = await health_service.run_all_checks()

        # Step 2: Daily selection
        task_result = await run_daily_selection(mock_session)

        # Verify results structure
        assert isinstance(health_report, dict)
        assert isinstance(task_result, dict)

        # Health check should have expected keys
        assert "is_healthy" in health_report
        assert "checks" in health_report

        # Task result should have expected keys
        assert "success" in task_result
        assert "products_count" in task_result

    @pytest.mark.asyncio
    async def test_error_handling_in_flow(self, mock_session):
        """Test error handling during validation."""
        # Simulate database error
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        # Health check should handle error gracefully
        health_service = HealthCheckService(mock_session)
        health_report = await health_service.run_all_checks()

        # Should still return a valid report
        assert isinstance(health_report, dict)
        assert health_report["is_healthy"] is False


# ── Report Generation Tests ────────────────────────────────────


class TestReportGeneration:
    """Test report generation."""

    def test_report_structure(self, tmp_path):
        """Test report JSON structure."""
        report = {
            "start_time": datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": 10.5,
            "health_check": {
                "is_healthy": True,
                "database": {"ok": True, "message": "OK"},
                "taobao_login": {"ok": True, "status": "ACTIVE"},
                "alibaba_login": {"ok": True, "status": "ACTIVE"},
                "feishu_config": {"ok": True, "enabled": False},
            },
            "task_result": {
                "success": True,
                "products_count": 10,
                "new_products_count": 5,
                "matched_count": 3,
                "report_sent": False,
            },
            "top_opportunities": [],
            "errors": [],
        }

        # Save and verify
        report_path = tmp_path / "test_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Load and verify
        with open(report_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["start_time"] == report["start_time"]
        assert loaded["task_result"]["success"] is True
        assert loaded["task_result"]["products_count"] == 10

    def test_report_with_errors(self, tmp_path):
        """Test report with errors."""
        report = {
            "start_time": datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": 5.0,
            "health_check": {
                "is_healthy": False,
                "database": {"ok": False, "message": "Connection failed"},
            },
            "task_result": {
                "success": False,
            },
            "top_opportunities": [],
            "errors": [
                {"type": "database_error", "message": "Connection refused"},
            ],
        }

        report_path = tmp_path / "error_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        with open(report_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["health_check"]["is_healthy"] is False
        assert len(loaded["errors"]) == 1
