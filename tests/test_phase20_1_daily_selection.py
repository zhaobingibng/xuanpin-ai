"""Tests for Phase 20 Task 1: Daily Selection Task Scheduling."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.daily_task_log import DailyTaskLog
from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.tasks.daily_selection_task import (
    load_selection_config,
    create_task_log,
    finish_task_log,
    send_failure_notification,
    run_daily_selection,
    daily_selection_job,
    _generate_mock_products,
)
from app.services.feishu_notification import FeishuNotificationService


# ── Configuration Tests ────────────────────────────────────────


class TestSelectionConfig:
    """Test selection configuration loading."""

    def test_load_default_config(self, tmp_path):
        """Test loading default config when file doesn't exist."""
        config = load_selection_config(str(tmp_path / "nonexistent.json"))
        assert config["top_count"] == 10
        assert config["min_score"] == 75
        assert config["shops"] == []

    def test_load_config_from_file(self, tmp_path):
        """Test loading config from file."""
        config_file = tmp_path / "selection_config.json"
        config_file.write_text(json.dumps({
            "shops": [{"name": "test_shop", "platform": "tmall"}],
            "top_count": 5,
            "min_score": 80,
        }))

        config = load_selection_config(str(config_file))
        assert config["top_count"] == 5
        assert config["min_score"] == 80
        assert len(config["shops"]) == 1

    def test_load_config_invalid_json(self, tmp_path):
        """Test loading invalid JSON config."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("invalid json")

        config = load_selection_config(str(config_file))
        # Should return defaults
        assert config["top_count"] == 10


# ── Task Log Tests ─────────────────────────────────────────────


class TestTaskLog:
    """Test task log management."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_create_task_log(self, mock_session):
        """Test creating task log."""
        log = await create_task_log(mock_session, "test_task")

        assert log.task_name == "test_task"
        assert log.status == "RUNNING"
        assert log.start_time is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_finish_task_log_success(self, mock_session):
        """Test finishing task log with success."""
        log = DailyTaskLog(task_name="test_task", start_time=datetime.now(), status="RUNNING")

        await finish_task_log(
            mock_session,
            log,
            status="SUCCESS",
            products_count=10,
            new_products_count=5,
            matched_count=3,
            report_sent=True,
        )

        assert log.status == "SUCCESS"
        assert log.end_time is not None
        assert log.products_count == 10
        assert log.new_products_count == 5
        assert log.matched_count == 3
        assert log.report_sent is True
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_finish_task_log_failed(self, mock_session):
        """Test finishing task log with failure."""
        log = DailyTaskLog(task_name="test_task", start_time=datetime.now(), status="RUNNING")

        await finish_task_log(
            mock_session,
            log,
            status="FAILED",
            error_message="Test error",
        )

        assert log.status == "FAILED"
        assert log.error_message == "Test error"


# ── Failure Notification Tests ─────────────────────────────────


class TestFailureNotification:
    """Test failure notification sending."""

    @pytest.mark.asyncio
    async def test_send_failure_notification(self):
        """Test sending failure notification."""
        mock_service = MagicMock(spec=FeishuNotificationService)
        mock_service.send_message = AsyncMock(return_value={"success": True})

        await send_failure_notification(mock_service, "test_task", "Test error")

        mock_service.send_message.assert_called_once()
        call_args = mock_service.send_message.call_args[0][0]
        assert "test_task" in call_args
        assert "Test error" in call_args
        assert "失败" in call_args

    @pytest.mark.asyncio
    async def test_send_failure_notification_error(self):
        """Test handling notification send error."""
        mock_service = MagicMock(spec=FeishuNotificationService)
        mock_service.send_message = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise
        await send_failure_notification(mock_service, "test_task", "Test error")


# ── Mock Products Tests ────────────────────────────────────────


class TestMockProducts:
    """Test mock product generation."""

    def test_generate_mock_products(self):
        """Test generating mock products."""
        shops = [
            {"name": "shop1", "platform": "tmall"},
            {"name": "shop2", "platform": "taobao"},
        ]

        products = _generate_mock_products(shops)

        assert len(products) == 4  # 2 shops * 2 items each
        for p in products:
            assert "name" in p
            assert "price" in p
            assert "shop" in p
            assert "url" in p

    def test_generate_mock_products_empty_shops(self):
        """Test generating mock products with empty shops."""
        products = _generate_mock_products([])
        assert len(products) == 0


# ── Main Task Tests ────────────────────────────────────────────


class TestRunDailySelection:
    """Test main daily selection task."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()

        # Mock query results
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing products
        session.execute.return_value = mock_result

        return session

    @pytest.mark.asyncio
    async def test_run_daily_selection_success(self, mock_session, tmp_path):
        """Test successful daily selection run."""
        # Create config file
        config_file = tmp_path / "selection_config.json"
        config_file.write_text(json.dumps({
            "shops": [{"name": "test_shop", "platform": "tmall"}],
            "top_count": 5,
        }))

        result = await run_daily_selection(mock_session, str(config_file))

        assert result["success"] is True
        assert result["products_count"] > 0
        assert result["new_products_count"] > 0

    @pytest.mark.asyncio
    async def test_run_daily_selection_default_config(self, mock_session):
        """Test daily selection with default config."""
        result = await run_daily_selection(mock_session)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_daily_selection_error_handling(self, mock_session):
        """Test error handling in daily selection."""
        # Make session.execute raise an error
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await run_daily_selection(mock_session)

        assert result["success"] is False
        assert "error" in result


# ── Scheduler Job Tests ────────────────────────────────────────


class TestDailySelectionJob:
    """Test scheduled job entry point."""

    @pytest.mark.asyncio
    async def test_daily_selection_job(self):
        """Test daily selection job."""
        with patch("app.database.base.get_async_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_factory.return_value.return_value = mock_session

            with patch("app.tasks.daily_selection_task.run_daily_selection", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {"success": True, "products_count": 5}

                await daily_selection_job()

                mock_run.assert_called_once()


# ── Scheduler Integration Tests ────────────────────────────────


class TestSchedulerIntegration:
    """Test scheduler integration."""

    def test_add_daily_selection(self):
        """Test adding daily selection job to scheduler."""
        from app.tasks.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_selection(hour=2, minute=0)

        assert job_id == "daily_selection"

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_selection"
        assert "Daily selection" in jobs[0]["name"]

    def test_add_daily_selection_custom_time(self):
        """Test adding daily selection with custom time."""
        from app.tasks.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_selection(hour=8, minute=30, job_id="custom_selection")

        assert job_id == "custom_selection"
