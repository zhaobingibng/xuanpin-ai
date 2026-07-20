"""History repository — snapshot creation and querying."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_history import ProductHistory


class HistoryRepository:
    """Async repository for ProductHistory snapshots.

    Dedup rule:
      Same product_id within the same minute → skip (no duplicate).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create(self, history: ProductHistory) -> ProductHistory:
        """Insert a new history record and return it."""
        self._session.add(history)
        await self._session.flush()
        return history

    # ── Snapshot ──────────────────────────────────────────────

    async def create_snapshot(
        self, product: Product
    ) -> ProductHistory | None:
        """Create a history snapshot from *product*.

        Returns the new ProductHistory, or None if a snapshot for
        the same product already exists within the current minute.
        """
        now = datetime.utcnow()
        minute_start = now.replace(second=0, microsecond=0)

        # Dedup: same product_id + same minute
        existing = await self._session.execute(
            select(ProductHistory).where(
                ProductHistory.product_id == product.id,
                func.strftime("%Y-%m-%d %H:%M", ProductHistory.record_time)
                == minute_start.strftime("%Y-%m-%d %H:%M"),
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug(
                "[history] skip duplicate: product_id={}, minute={}",
                product.id,
                minute_start.strftime("%H:%M"),
            )
            return None

        history = ProductHistory(
            product_id=product.id,
            price=product.price,
            sales_24h=product.sales_24h,
            viewers=product.viewers,
            ai_score=product.ai_score,
        )
        return await self.create(history)

    # ── Query ─────────────────────────────────────────────────

    async def get_history(
        self, product_id: int, limit: int = 30
    ) -> Sequence[ProductHistory]:
        """Fetch history for *product_id*, newest first."""
        stmt = (
            select(ProductHistory)
            .where(ProductHistory.product_id == product_id)
            .order_by(ProductHistory.record_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
