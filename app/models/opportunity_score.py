"""OpportunityScore ORM model — 跟卖机会指数评分."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpportunityScore(Base):
    """跟卖机会指数评分模型。

    评分维度（总分100）：
    - new_product_score: 新品价值 (0-25)
    - shop_score: 店铺质量 (0-20)
    - supplier_score: 供应链能力 (0-25)
    - profit_score: 利润空间 (0-20)
    - competition_score: 竞争情况 (0-10)
    - total_score: 总分

    推荐等级：
    - 90-100: ★★★★★ 强烈推荐
    - 75-89: ★★★★ 值得研究
    - 60-74: ★★★ 观察
    - <60: 暂不推荐
    """

    __tablename__ = "opportunity_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True, comment="商品ID"
    )

    # 评分维度
    new_product_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="新品价值 (0-25)")
    shop_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="店铺质量 (0-20)")
    supplier_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="供应链能力 (0-25)")
    profit_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="利润空间 (0-20)")
    competition_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="竞争情况 (0-10)")

    # 总分
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="总分 (0-100)")

    # 推荐
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False, default="暂不推荐", comment="推荐等级")

    # 时间
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="评分时间"
    )

    def __repr__(self) -> str:
        return (
            f"<OpportunityScore(product_id={self.product_id}, "
            f"total={self.total_score:.1f}, rec='{self.recommendation}')>"
        )

    @property
    def stars(self) -> str:
        """返回星级表示。"""
        level_stars = {
            "★★★★★ 强烈推荐": "★★★★★",
            "★★★★ 值得研究": "★★★★",
            "★★★ 观察": "★★★",
            "暂不推荐": "★",
        }
        return level_stars.get(self.recommendation, "★")
