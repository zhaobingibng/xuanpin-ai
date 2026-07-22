"""Feishu (Lark) notification service for daily reports."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class FeishuNotificationService:
    """飞书通知服务。

    支持发送 Markdown 格式的日报到飞书群。

    配置方式：
    - config/feishu.json
    - 环境变量 FEISHU_WEBHOOK_URL / FEISHU_SECRET

    使用示例：
        service = FeishuNotificationService()
        await service.send_message("Hello World")
        await service.send_daily_report(report_text)
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        secret: str | None = None,
        config_path: str | None = None,
    ) -> None:
        """Initialize feishu notification service.

        Args:
            webhook_url: Feishu webhook URL (overrides config).
            secret: Feishu webhook secret (overrides config).
            config_path: Path to config file.
        """
        self._webhook_url = webhook_url
        self._secret = secret
        self._enabled = True

        # Load config if not provided directly
        if not webhook_url:
            self._load_config(config_path)

    def _load_config(self, config_path: str | None = None) -> None:
        """Load configuration from JSON file."""
        if config_path is None:
            # Default path
            config_file = Path(__file__).parent.parent.parent / "config" / "feishu.json"
        else:
            config_file = Path(config_path)

        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self._enabled = config.get("enabled", False)
                self._webhook_url = self._webhook_url or config.get("webhook_url", "")
                self._secret = self._secret or config.get("secret", "")
            except Exception as e:
                logger.warning(f"Failed to load feishu config: {e}")
                self._enabled = False
        else:
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Check if feishu notification is enabled."""
        return self._enabled and bool(self._webhook_url)

    def _generate_sign(self, timestamp: str) -> str:
        """Generate signature for webhook request.

        Args:
            timestamp: Unix timestamp string.

        Returns:
            Base64 encoded signature.
        """
        if not self._secret:
            return ""

        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    async def send_message(
        self,
        content: str,
        *,
        msg_type: str = "text",
    ) -> dict[str, Any]:
        """Send message to feishu.

        Args:
            content: Message content.
            msg_type: Message type ("text" or "post").

        Returns:
            Response dict with "success" and "message" keys.
        """
        if not self.is_enabled:
            logger.info("[Feishu] Notification disabled, skipping")
            return {"success": False, "message": "Notification disabled"}

        timestamp = str(int(time.time()))
        sign = self._generate_sign(timestamp)

        if msg_type == "text":
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "text",
                "content": {"text": content},
            }
        elif msg_type == "post":
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "选品日报",
                            "content": [[{"tag": "text", "text": content}]],
                        }
                    }
                },
            }
        else:
            return {"success": False, "message": f"Unknown msg_type: {msg_type}"}

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("code") == 0:
                    logger.info("[Feishu] Message sent successfully")
                    return {"success": True, "message": "Sent"}
                else:
                    logger.warning(f"[Feishu] Send failed: {result}")
                    return {"success": False, "message": result.get("msg", "Unknown error")}

        except Exception as e:
            logger.warning(f"[Feishu] Send error: {e}")
            return {"success": False, "message": str(e)}

    async def send_daily_report(self, report_text: str) -> dict[str, Any]:
        """Send daily opportunity report to feishu.

        Args:
            report_text: Formatted report text (Markdown or plain text).

        Returns:
            Response dict.
        """
        return await self.send_message(report_text, msg_type="text")
