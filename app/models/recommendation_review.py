"""RecommendationReview ORM model — track recommendation effectiveness."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RecommendationReview(Base):
    """推荐复盘记录。"""

    __tablename__ = "recommendation_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="关联推荐记录 ID (DailyReportItem.id)"
    )
    product_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="关联商品 ID"
    )
    review_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="复盘日期"
    )
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL",
        comment="复盘结果: SUCCESS/NORMAL/FAILED"
    )
    sales_change: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="销量变化百分比"
    )
    trend_change: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="趋势评分变化"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return (
            f"<RecommendationReview(id={self.id}, product_id={self.product_id}, "
            f"result='{self.result}')>"
        )
