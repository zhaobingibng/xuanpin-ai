"""SupplyChainMatch ORM model — supply chain matching results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SupplyChainMatch(Base):
    """供应链匹配结果 — 记录淘宝商品与1688供应商的匹配关系。"""

    __tablename__ = "supply_chain_match"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联淘宝商品 ID",
    )
    source_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联1688商品 ID (可选，Mock数据可能无对应Product)",
    )
    source_product_external_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="1688商品外部标识 (Mock ID)"
    )
    match_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="匹配得分 0-1"
    )
    match_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="title", comment="匹配类型: title/combined"
    )
    cost_price: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="1688采购价"
    )
    sell_price: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="淘宝售价"
    )
    profit_margin: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="利润率 (%)"
    )
    profit_amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="利润额"
    )
    platform_fee_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.05, comment="平台佣金率"
    )
    shipping_cost: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0, comment="运费估算"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MATCHED",
        index=True, comment="状态: MATCHED/REVIEWED/REJECTED"
    )
    matched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="匹配时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return (
            f"<SupplyChainMatch(id={self.id}, product_id={self.product_id}, "
            f"score={self.match_score:.2f}, margin={self.profit_margin:.1f}%)>"
        )
