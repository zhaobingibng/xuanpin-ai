"""SupplierProduct ORM model — 1688供应商商品数据."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SupplierProductDB(Base):
    """1688供应商商品模型。

    存储从1688搜索页面捕获的供应商商品数据。
    数据来源：EventParser 解析的 ParsedProduct。

    字段说明：
    - source: 数据来源平台 (默认 "1688")
    - offer_id: 1688商品ID
    - title: 商品标题
    - price: 商品价格
    - sales: 销量
    - shop_name: 供应商名称
    - url: 商品链接
    - image: 商品图片
    """

    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 来源
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1688", comment="数据来源平台"
    )

    # 1688商品信息
    offer_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, unique=True, comment="1688商品ID"
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", comment="商品标题"
    )
    price: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="商品价格"
    )
    sales: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="销量"
    )
    shop_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="供应商名称"
    )
    url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="商品链接"
    )
    image: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="商品图片"
    )

    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierProductDB(offer_id={self.offer_id!r}, "
            f"title={self.title[:30]!r}, price={self.price})>"
        )
