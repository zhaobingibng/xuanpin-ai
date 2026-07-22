"""SupplierMatch ORM model — 供应链匹配结果（含 ProductMatcher 多维评分）."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SupplierMatch(Base):
    """供应链匹配结果模型。

    记录淘宝新品与1688供应商的匹配关系。

    字段说明：
    - product_id: 关联淘宝商品ID
    - supplier_product_id: 关联1688供应商商品ID（supplier_products 表）
    - supplier_title: 1688供应商商品标题
    - supplier_url: 1688供应商商品链接
    - supplier_price: 1688供应商价格
    - similarity_score: 融合最终评分 [0, 1]（= final_score）
    - text_score: 文本相似度评分 [0, 1]
    - feature_score: 特征匹配评分 [0, 1]
    - rank: 在当前 product 的匹配结果中排名 (1-based)
    - estimated_profit: 预估利润额
    - profit_margin: 利润率 (%)
    """

    __tablename__ = "supplier_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True, comment="淘宝商品ID"
    )

    # 1688供应商关联
    supplier_product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("supplier_products.id"), nullable=True, index=True, comment="1688供应商商品ID"
    )

    # 1688供应商信息
    supplier_title: Mapped[str] = mapped_column(String(500), nullable=False, comment="1688商品标题")
    supplier_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="1688商品链接")
    supplier_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="1688价格")

    # 多维匹配评分
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="融合最终评分 [0,1]")
    text_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None, comment="文本相似度 [0,1]")
    feature_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None, comment="特征匹配评分 [0,1]")
    image_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None, comment="图片相似度 [0,1]")

    # 排名
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None, comment="在当前商品匹配中排名")

    # 利润计算
    estimated_profit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="预估利润")
    profit_margin: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="利润率 (%)")

    # 时间
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="匹配时间"
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierMatch(product_id={self.product_id}, "
            f"supplier_product_id={self.supplier_product_id}, "
            f"similarity={self.similarity_score:.3f}, rank={self.rank})>"
        )

    @property
    def final_score(self) -> float:
        """统一命名别名 — 返回 similarity_score（融合最终评分）."""
        return self.similarity_score
