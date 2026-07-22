"""SupplierProductRepository — 1688供应商商品数据持久化."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.event_parser import ParsedProduct
from app.models.supplier_product import SupplierProductDB


class SupplierProductRepository:
    """Async repository for 1688 supplier product persistence.

    Provides methods to save parsed products and query by offer_id or keyword.

    Usage:
        repo = SupplierProductRepository(session)
        await repo.save_products(parsed_products)
        product = await repo.get_by_offer_id("123456789")
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Save ──────────────────────────────────────────────────

    async def save_products(self, products: list[ParsedProduct]) -> list[SupplierProductDB]:
        """Save a list of parsed products to the database.

        Uses offer_id as unique key: updates existing records, inserts new ones.

        Args:
            products: List of ParsedProduct from EventParser.

        Returns:
            List of saved SupplierProductDB instances.
        """
        saved: list[SupplierProductDB] = []

        for p in products:
            if not p.offer_id:
                continue

            # Check if already exists
            existing = await self.get_by_offer_id(p.offer_id)

            if existing:
                # Update existing record
                existing.title = p.title
                existing.price = p.price
                existing.sales = p.sales
                existing.shop_name = p.shop_name
                existing.url = p.url
                existing.image = p.image
                existing.source = p.source
                saved.append(existing)
            else:
                # Insert new record
                db_product = SupplierProductDB(
                    source=p.source,
                    offer_id=p.offer_id,
                    title=p.title,
                    price=p.price,
                    sales=p.sales,
                    shop_name=p.shop_name,
                    url=p.url,
                    image=p.image,
                )
                self._session.add(db_product)
                saved.append(db_product)

        await self._session.flush()
        return saved

    # ── Queries ───────────────────────────────────────────────

    async def get_by_offer_id(self, offer_id: str) -> SupplierProductDB | None:
        """Get a supplier product by its 1688 offer_id.

        Args:
            offer_id: 1688 product ID.

        Returns:
            SupplierProductDB or None if not found.
        """
        stmt = select(SupplierProductDB).where(
            SupplierProductDB.offer_id == offer_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_keyword(self, keyword: str) -> Sequence[SupplierProductDB]:
        """Search supplier products by title keyword.

        Args:
            keyword: Search keyword (case-insensitive LIKE match).

        Returns:
            List of matching SupplierProductDB.
        """
        stmt = (
            select(SupplierProductDB)
            .where(SupplierProductDB.title.contains(keyword))
            .order_by(SupplierProductDB.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_all(self) -> Sequence[SupplierProductDB]:
        """Get all supplier products.

        Returns:
            List of all SupplierProductDB records.
        """
        stmt = select(SupplierProductDB).order_by(
            SupplierProductDB.updated_at.desc()
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Get total count of supplier products.

        Returns:
            Number of records.
        """
        from sqlalchemy import func
        stmt = select(func.count()).select_from(SupplierProductDB)
        result = await self._session.execute(stmt)
        return result.scalar_one()
