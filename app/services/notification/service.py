"""NotificationService — failure alerts via console and webhook."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger


class NotificationService:
    """失败通知服务。

    Supports:
    - Console logging (always active)
    - Webhook (extensible, POST JSON to URL)

    Triggers:
    - 采集失败
    - Cookie 失效
    - 系统异常
    """

    # Notification types
    CRAWL_FAILED = "CRAWL_FAILED"
    COOKIE_EXPIRED = "COOKIE_EXPIRED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    TASK_FAILED = "TASK_FAILED"

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url
        self._history: list[dict] = []

    @property
    def history(self) -> list[dict]:
        """Return notification history."""
        return list(self._history)

    @property
    def history_count(self) -> int:
        return len(self._history)

    async def notify(
        self,
        notification_type: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict:
        """发送通知。

        Args:
            notification_type: 通知类型常量。
            message: 通知消息。
            details: 附加详情。

        Returns:
            Notification record dict.
        """
        from app.services.metrics.service import MetricsService

        record = {
            "type": notification_type,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "delivered": False,
        }

        # Console notification (always active)
        self._console_notify(record)

        # Webhook notification (if configured)
        if self._webhook_url:
            await self._webhook_notify(record)

        self._history.append(record)

        # Also append to shared history for DashboardService
        try:
            from app.services.dashboard.service import _notification_history
            _notification_history.append(record)
        except Exception:
            pass  # Dashboard import failure should not block notification

        # Update metrics
        MetricsService.inc_notification_sent()

        return record

    def _console_notify(self, record: dict) -> None:
        """Output notification to console via loguru."""
        logger.warning(
            "[Notification] {} — {}: {}",
            record["type"],
            record["message"],
            record.get("details", {}),
        )
        record["delivered"] = True

    async def _webhook_notify(self, record: dict) -> None:
        """POST notification to webhook URL (best-effort)."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                await client.post(
                    self._webhook_url,
                    json=record,
                    timeout=10.0,
                )
            logger.info("[Notification] Webhook delivered to {}", self._webhook_url)
        except Exception as e:
            logger.warning("[Notification] Webhook delivery failed: {}", e)
