"""Async CRUD service for Product."""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class ProductService:
    """Provides async CRUD operations for Product entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create(self, **kwargs) -> Product:
        """Add a new product and return it."""
        product = Product(**kwargs)
        self._session.add(product)
        await self._session.commit()
        await self._session.refresh(product)
        return product

    # ── Read ──────────────────────────────────────────────────

    async def get_by_id(self, product_id: int) -> Product | None:
        """Fetch a single product by primary key."""
        return await self._session.get(Product, product_id)

    async def list_all(
        self,
        *,
        platform: str | None = None,
        shop: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Product]:
        """List products with optional filters and pagination."""
        stmt = select(Product)
        if platform:
            stmt = stmt.where(Product.platform == platform)
        if shop:
            stmt = stmt.where(Product.shop == shop)
        stmt = stmt.order_by(Product.id).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ── Update ────────────────────────────────────────────────

    async def update(self, product_id: int, **kwargs) -> Product | None:
        """Update an existing product; return None if not found."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        await self._session.commit()
        await self._session.refresh(product)
        return product

    # ── Delete ────────────────────────────────────────────────

    async def delete(self, product_id: int) -> bool:
        """Delete a product by id. Return True if deleted, False if not found."""
        product = await self.get_by_id(product_id)
        if product is None:
            return False
        await self._session.delete(product)
        await self._session.commit()
        return True
