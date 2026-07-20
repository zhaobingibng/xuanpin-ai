"""ScoringConfig ORM model — dynamic scoring weight configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

# ── Default weights ──────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "sales_weight": 0.30,
    "trend_weight": 0.25,
    "viewer_weight": 0.15,
    "price_weight": 0.15,
    "competition_weight": 0.15,
}


class ScoringConfig(Base):
    """评分权重配置。"""

    __tablename__ = "scoring_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", comment="配置名称"
    )
    sales_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.30, comment="销量权重"
    )
    trend_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.25, comment="趋势权重"
    )
    viewer_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.15, comment="浏览热度权重"
    )
    price_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.15, comment="价格竞争力权重"
    )
    competition_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.15, comment="竞争度权重"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="版本号"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否生效"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return (
            f"<ScoringConfig(id={self.id}, name='{self.name}', "
            f"version={self.version}, active={self.is_active})>"
        )

    def to_weights_dict(self) -> dict[str, float]:
        """转为权重字典。"""
        return {
            "sales_weight": self.sales_weight,
            "trend_weight": self.trend_weight,
            "viewer_weight": self.viewer_weight,
            "price_weight": self.price_weight,
            "competition_weight": self.competition_weight,
        }
