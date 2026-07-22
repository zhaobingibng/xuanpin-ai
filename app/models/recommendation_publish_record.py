"""RecommendationPublishRecord ORM model — 推荐商品发布记录 (Phase 46.4).

独立于 recommendation_status 和 recommendation_reviews：
- recommendation_status：人工审核状态 (NEW/REVIEWED/APPROVED/REJECTED/PUBLISHED)
- recommendation_publish_records：发布执行记录 (PENDING/SUCCESS/FAILED)
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PublishStatus(str, enum.Enum):
    """发布执行状态。"""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RecommendationPublishRecord(Base):
    """推荐商品发布记录 — 每次发布尝试一条记录。

    与 RecommendationStatus 的关系：
    - APPROVED → 可发起发布，创建 PENDING 记录
    - 发布成功 → record.status=SUCCESS, RecommendationStatus.status→PUBLISHED
    - 发布失败 → record.status=FAILED, RecommendationStatus 保持 APPROVED（可重试）
    """

    __tablename__ = "recommendation_publish_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联商品 ID",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PublishStatus.PENDING.value,
        comment="发布状态: PENDING/SUCCESS/FAILED",
    )

    platform: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="目标发布平台（taobao/tmall/1688 等）",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="失败原因"
    )

    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="重试次数"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="实际发布时间"
    )

    def __repr__(self) -> str:
        return (
            f"<RecommendationPublishRecord(id={self.id}, "
            f"product_id={self.product_id}, status='{self.status}')>"
        )
