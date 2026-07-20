"""ProductTag ORM model — tag taxonomy for knowledge base."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProductTag(Base):
    """商品标签（知识库标签体系）。"""

    __tablename__ = "product_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True, comment="标签名称"
    )
    type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
        comment="标签类型: CATEGORY/SUCCESS_PATTERN/FAIL_PATTERN/TREND"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", comment="标签描述"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return f"<ProductTag(id={self.id}, name='{self.name}', type='{self.type}')>"
