"""Tests for Phase 9.7.6 — NotificationService.

Covers: notify(), console delivery, history, notification types.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.notification.service import NotificationService


# ── TestNotificationService ────────────────────────────────────


class TestNotificationService:
    """NotificationService notify and history."""

    @pytest.mark.anyio
    async def test_notify_console(self):
        ns = NotificationService()
        record = await ns.notify(
            NotificationService.CRAWL_FAILED,
            "小红书采集失败",
            details={"keyword": "蓝牙耳机"},
        )

        assert record["type"] == "CRAWL_FAILED"
        assert record["message"] == "小红书采集失败"
        assert record["details"]["keyword"] == "蓝牙耳机"
        assert record["delivered"] is True

    @pytest.mark.anyio
    async def test_history_recorded(self):
        ns = NotificationService()
        await ns.notify(NotificationService.SYSTEM_ERROR, "DB down")
        await ns.notify(NotificationService.COOKIE_EXPIRED, "XHS cookie expired")

        assert ns.history_count == 2
        assert ns.history[0]["type"] == "SYSTEM_ERROR"
        assert ns.history[1]["type"] == "COOKIE_EXPIRED"

    @pytest.mark.anyio
    async def test_no_webhook_by_default(self):
        ns = NotificationService()
        record = await ns.notify(NotificationService.TASK_FAILED, "task failed")
        # Without webhook_url, should still be delivered via console
        assert record["delivered"] is True

    @pytest.mark.anyio
    async def test_webhook_delivery_attempted(self):
        ns = NotificationService(webhook_url="https://hooks.example.com/alert")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await ns.notify(NotificationService.CRAWL_FAILED, "test")

    @pytest.mark.anyio
    async def test_webhook_failure_does_not_raise(self):
        ns = NotificationService(webhook_url="https://invalid.example.com")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("network"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            # Should not raise
            record = await ns.notify(NotificationService.SYSTEM_ERROR, "test")
            assert record["type"] == "SYSTEM_ERROR"

    @pytest.mark.anyio
    async def test_empty_details_default(self):
        ns = NotificationService()
        record = await ns.notify(NotificationService.CRAWL_FAILED, "msg")
        assert record["details"] == {}

    @pytest.mark.anyio
    async def test_timestamp_present(self):
        ns = NotificationService()
        record = await ns.notify(NotificationService.CRAWL_FAILED, "msg")
        assert "timestamp" in record
        assert len(record["timestamp"]) > 0


# ── TestNotificationTypes ──────────────────────────────────────


class TestNotificationTypes:
    """Notification type constants."""

    def test_crawl_failed(self):
        assert NotificationService.CRAWL_FAILED == "CRAWL_FAILED"

    def test_cookie_expired(self):
        assert NotificationService.COOKIE_EXPIRED == "COOKIE_EXPIRED"

    def test_system_error(self):
        assert NotificationService.SYSTEM_ERROR == "SYSTEM_ERROR"

    def test_task_failed(self):
        assert NotificationService.TASK_FAILED == "TASK_FAILED"
