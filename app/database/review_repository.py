"""Review repository — persist and query recommendation review records."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation_review import RecommendationReview


class ReviewRepository:
    """推荐复盘数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def save_review(self, review: RecommendationReview) -> RecommendationReview:
        """保存单条复盘记录。"""
        self._session.add(review)
        await self._session.flush()
        return review

    # ── Query ─────────────────────────────────────────────────

    async def get_reviews(self, limit: int = 30) -> Sequence[RecommendationReview]:
        """获取最近的复盘记录。"""
        stmt = (
            select(RecommendationReview)
            .order_by(RecommendationReview.review_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_reviews_by_date(self, review_date: date) -> Sequence[RecommendationReview]:
        """获取指定日期的复盘记录。"""
        stmt = (
            select(RecommendationReview)
            .where(RecommendationReview.review_date == review_date)
            .order_by(RecommendationReview.id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_accuracy(self) -> dict[str, float]:
        """计算总体准确率。

        Returns:
            {"accuracy": float, "total": int, "success": int}
        """
        total_stmt = select(func.count(RecommendationReview.id))
        total_result = await self._session.execute(total_stmt)
        total = total_result.scalar() or 0

        if total == 0:
            return {"accuracy": 0.0, "total": 0, "success": 0}

        success_stmt = select(func.count(RecommendationReview.id)).where(
            RecommendationReview.result == "SUCCESS"
        )
        success_result = await self._session.execute(success_stmt)
        success = success_result.scalar() or 0

        accuracy = round(success / total * 100, 1)
        return {"accuracy": accuracy, "total": total, "success": success}

    async def get_product_reviews(
        self, product_id: int
    ) -> Sequence[RecommendationReview]:
        """获取指定商品的历史复盘记录。"""
        stmt = (
            select(RecommendationReview)
            .where(RecommendationReview.product_id == product_id)
            .order_by(RecommendationReview.review_date.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
