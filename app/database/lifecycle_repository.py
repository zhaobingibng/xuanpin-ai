"""Lifecycle repository — persist and query lifecycle stages."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class LifecycleRepository:
    """Async repository for lifecycle stage persistence on Product.

    Methods save analysis results to the Product.lifecycle_stage column
    and provide stage-based queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Save ──────────────────────────────────────────────────

    async def save_result(self, result: dict[str, Any]) -> Product | None:
        """Save lifecycle analysis result to the Product record.

        Args:
            result: Dict with at least 'product_id' and 'stage'.

        Returns:
            Updated Product, or None if not found.
        """
        stmt = select(Product).where(Product.id == result["product_id"])
        row = await self._session.execute(stmt)
        product = row.scalar_one_or_none()
        if product is None:
            return None
        product.lifecycle_stage = result["stage"]
        await self._session.flush()
        return product

    # ── Queries ───────────────────────────────────────────────

    async def get_latest(self, product_id: int) -> str | None:
        """Get the latest lifecycle stage for a product."""
        stmt = select(Product.lifecycle_stage).where(Product.id == product_id)
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def get_hot_products(self) -> Sequence[Product]:
        """Get all products currently in HOT stage."""
        stmt = (
            select(Product)
            .where(Product.lifecycle_stage == "HOT")
            .order_by(Product.sales_24h.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_rising_products(self) -> Sequence[Product]:
        """Get all products currently in RISING stage."""
        stmt = (
            select(Product)
            .where(Product.lifecycle_stage == "RISING")
            .order_by(Product.sales_24h.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
