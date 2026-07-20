"""Strategy repository — persist and query product strategy records."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_strategy import ProductStrategy


class StrategyRepository:
    """商品运营方案数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_strategy(self, strategy: ProductStrategy) -> ProductStrategy:
        """保存一条运营方案。"""
        self._session.add(strategy)
        await self._session.flush()
        return strategy

    async def get_strategy(self, product_id: int) -> ProductStrategy | None:
        """获取指定商品的最新运营方案。"""
        stmt = (
            select(ProductStrategy)
            .where(ProductStrategy.product_id == product_id)
            .order_by(ProductStrategy.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, product_id: int, limit: int = 10) -> Sequence[ProductStrategy]:
        """获取指定商品的历史运营方案（按时间降序）。"""
        stmt = (
            select(ProductStrategy)
            .where(ProductStrategy.product_id == product_id)
            .order_by(ProductStrategy.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
