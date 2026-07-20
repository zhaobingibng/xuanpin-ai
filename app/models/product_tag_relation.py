"""ProductTagRelation ORM model — many-to-many product↔tag binding."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProductTagRelation(Base):
    """商品—标签关联关系。"""

    __tablename__ = "product_tag_relations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="商品 ID"
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="标签 ID"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, comment="置信度 0-1"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="AI",
        comment="来源: AI/MANUAL/LEARNING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    __table_args__ = (
        UniqueConstraint("product_id", "tag_id", name="uq_product_tag"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductTagRelation(product_id={self.product_id}, "
            f"tag_id={self.tag_id}, confidence={self.confidence})>"
        )
