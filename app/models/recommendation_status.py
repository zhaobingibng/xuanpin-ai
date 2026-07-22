"""RecommendationStatus ORM model — 推荐池人工审核状态 (Phase 46.2).

与已有 recommendation_reviews 表（复盘效果跟踪）完全独立：
- recommendation_status：人工审核状态 NEW→REVIEWED→APPROVED→REJECTED + 备注
- recommendation_reviews：复盘效果跟踪 SUCCESS/NORMAL/FAILED

推荐池本身是聚合查询（live view），不物化存储。
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PoolStatus(str, enum.Enum):
    """推荐池审核状态。

    流转规则（Service 层校验）：
        NEW       → REVIEWED / APPROVED / REJECTED
        REVIEWED  → APPROVED / REJECTED / NEW
        APPROVED  → REJECTED / REVIEWED / PUBLISHED
        REJECTED  → NEW
        PUBLISHED → (不可逆，仅可查看)
    """

    NEW = "NEW"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class RecommendationStatus(Base):
    """推荐池审核状态 — 仅持久化人工审核信息。

    不冗余商品/供应商/评分数据——这些通过聚合查询实时 JOIN。
    UNIQUE(product_id, report_date) 保证同一商品同一天仅一条状态记录。
    """

    __tablename__ = "recommendation_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联商品 ID",
    )
    report_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="推荐日期（对应 DailyReport.report_date）",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PoolStatus.NEW.value,
        comment="审核状态: NEW/REVIEWED/APPROVED/REJECTED",
    )
    review_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="审核备注"
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="首次审核时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("product_id", "report_date", name="uq_rs_product_date"),
    )

    # ── Enum helpers ──────────────────────────────────────────

    @property
    def status_enum(self) -> PoolStatus:
        """返回 PoolStatus 枚举值。"""
        return PoolStatus(self.status)

    def set_status(self, value: PoolStatus) -> None:
        """设置状态（枚举 → 字符串）。"""
        self.status = value.value

    def __repr__(self) -> str:
        return (
            f"<RecommendationStatus(id={self.id}, product_id={self.product_id}, "
            f"date={self.report_date}, status='{self.status}')>"
        )
