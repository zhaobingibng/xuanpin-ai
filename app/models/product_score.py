"""ProductScore ORM model — 新品价值评分."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProductScore(Base):
    """新品价值评分模型。

    评分维度（总分100）：
    - shop_score: 店铺权重 (0-30)
    - price_score: 价格评分 (0-20)
    - category_score: 类目潜力 (0-15)
    - newness_score: 新品程度 (0-25)
    - completeness_score: 数据完整度 (0-10)
    - total_score: 总分

    推荐等级：
    - 90-100: ★★★★★ 强烈关注
    - 75-89: ★★★★ 推荐关注
    - 60-74: ★★★ 观察
    - <60: 暂不推荐
    """

    __tablename__ = "product_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True, comment="商品ID"
    )

    # 评分维度
    shop_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="店铺权重 (0-30)")
    price_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="价格评分 (0-20)")
    category_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="类目潜力 (0-15)")
    newness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="新品程度 (0-25)")
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="数据完整度 (0-10)")

    # 总分
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="总分 (0-100)")

    # 推荐等级
    recommend_level: Mapped[str] = mapped_column(String(50), nullable=False, default="暂不推荐", comment="推荐等级")

    # 时间
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="评分时间"
    )

    def __repr__(self) -> str:
        return f"<ProductScore(product_id={self.product_id}, total={self.total_score:.1f}, level='{self.recommend_level}')>"

    @property
    def stars(self) -> str:
        """返回星级表示。"""
        level_stars = {
            "★★★★★ 强烈关注": "★★★★★",
            "★★★★ 推荐关注": "★★★★",
            "★★★ 观察": "★★★",
            "暂不推荐": "★",
        }
        return level_stars.get(self.recommend_level, "★")
