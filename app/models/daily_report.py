"""DailyReport ORM models — persisted daily selection reports."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DailyReport(Base):
    """每日选品报告记录。"""

    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(
        Date, nullable=False, unique=True, index=True, comment="报告日期"
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="商品总数")
    hot_products: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="爆款数量")
    potential_products: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="潜力商品数量")
    average_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="平均评分")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    items: Mapped[list[DailyReportItem]] = relationship(
        "DailyReportItem", back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DailyReport(id={self.id}, date={self.report_date}, total={self.total})>"


class DailyReportItem(Base):
    """日报中的单条商品记录。"""

    __tablename__ = "daily_report_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("daily_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联日报 ID",
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="商品 ID")
    rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="排名")
    name: Mapped[str] = mapped_column(String(500), nullable=False, comment="商品名称")
    platform: Mapped[str] = mapped_column(String(100), nullable=False, comment="平台")
    image: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="商品图片 URL")
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="价格")
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="评分")
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="等级")
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="推荐理由(JSON)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    report: Mapped[DailyReport] = relationship("DailyReport", back_populates="items")

    def __repr__(self) -> str:
        return f"<DailyReportItem(id={self.id}, report_id={self.report_id}, rank={self.rank})>"
