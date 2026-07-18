"""Product ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Product(Base):
    """商品数据模型。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="商品名称")
    platform: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="平台")
    shop: Mapped[str] = mapped_column(String(200), nullable=False, comment="店铺")
    image: Mapped[str | None] = mapped_column(Text, nullable=True, comment="商品主图 URL")
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="商品价格")
    viewers: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="当前浏览人数")
    sales_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="24小时销量")
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="AI评分")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', platform='{self.platform}')>"
