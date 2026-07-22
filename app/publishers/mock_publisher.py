"""MockPublisher — 模拟发布平台 (Phase 47.1).

包含发布相关的 DTO 和具体实现。
所有类都在一个文件中（项目宪法 Article V, XI：不设接口，不设工厂）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from loguru import logger

from app.config.publish import publish_settings


# ── DTO ─────────────────────────────────────────────────────


@dataclass
class PublishContext:
    """发布上下文 —— 传递给 MockPublisher 的输入。"""

    product_id: int
    """商品 ID。"""

    platform: str
    """目标平台（taobao/tmall/1688/douyin/shopify/amazon）。"""

    report_date: date
    """推荐日期。"""

    product: dict[str, Any] | None = None
    """商品信息（name, shop, price, image 等）。"""

    supplier_match: dict[str, Any] | None = None
    """供应链匹配信息（1688 supplier 匹配结果）。"""

    supplier_product: dict[str, Any] | None = None
    """供应商商品信息。"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """扩展元数据（平台特定参数）。"""


@dataclass
class PublishResult:
    """发布结果 —— MockPublisher 的输出。"""

    success: bool
    """发布是否成功。"""

    platform: str
    """目标平台。"""

    message: str
    """成功/失败描述信息。"""

    external_id: str | None = None
    """外部平台 ID（如淘宝商品 ID）。"""

    published_at: datetime | None = None
    """发布时间（成功时设置）。"""


# ── Concrete Publisher ──────────────────────────────────────


class MockPublisher:
    """模拟发布器 —— 85% 成功率随机结果。

    目前唯一的 Publisher 实现。
    项目宪法 Article V：只有一个实现时不设接口。需要新增平台时直接从此类扩展。

    Usage::

        pub = MockPublisher()
        result = await pub.publish(context)
        assert result.success in (True, False)
    """

    def __init__(self, success_rate: float | None = None) -> None:
        """初始化模拟发布器。

        Args:
            success_rate: 模拟成功率 (0.0 ~ 1.0)，None 则使用 publish_settings。
        """
        self._success_rate = success_rate if success_rate is not None else publish_settings.success_rate

    async def publish(self, context: PublishContext) -> PublishResult:
        """模拟发布 —— 随机成功/失败。

        Args:
            context: 发布上下文。

        Returns:
            PublishResult 包含成功/失败信息。
        """
        success = random.random() < self._success_rate

        if success:
            logger.info(
                "[MockPublisher] product_id={}: 模拟发布成功 ({})",
                context.product_id, context.platform,
            )
            return PublishResult(
                success=True,
                platform=context.platform,
                message=f"模拟发布成功 — {context.platform}",
                external_id=f"mock_{context.product_id}_{int(datetime.now(timezone.utc).timestamp())}",
                published_at=datetime.now(),
            )
        else:
            logger.warning(
                "[MockPublisher] product_id={}: 模拟发布失败 ({})",
                context.product_id, context.platform,
            )
            return PublishResult(
                success=False,
                platform=context.platform,
                message="模拟发布失败（未来接入真实 API）",
            )
