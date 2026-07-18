"""ProductHistory ORM model — time-series snapshots of product metrics."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProductHistory(Base):
    """商品历史数据快照，按时间序列记录价格、销量、热度变化。"""

    __tablename__ = "product_history"

    __table_args__ = (
        Index("ix_history_product_record", "product_id", "record_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联商品 ID",
    )
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="商品价格")
    sales_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="24小时销量")
    viewers: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="当前浏览人数")
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="AI评分")
    record_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="记录时间",
    )

    def __repr__(self) -> str:
        return (
            f"<ProductHistory(id={self.id}, product_id={self.product_id}, "
            f"price={self.price}, record_time='{self.record_time}')>"
        )
