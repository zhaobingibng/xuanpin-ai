"""ProductStrategy ORM model — AI-generated marketing strategy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProductStrategy(Base):
    """AI生成的商品运营方案。"""

    __tablename__ = "product_strategies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="商品 ID"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="运营标题"
    )
    selling_points: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", comment="卖点列表 (JSON)"
    )
    xiaohongshu_copy: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="小红书文案"
    )
    xianyu_copy: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="闲鱼文案"
    )
    price_strategy: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", comment="价格策略 (JSON)"
    )
    profit_analysis: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", comment="利润分析 (JSON)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return f"<ProductStrategy(id={self.id}, product_id={self.product_id}, title='{self.title}')>"
