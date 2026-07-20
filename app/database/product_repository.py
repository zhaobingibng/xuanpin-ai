"""Product repository — create / update / upsert with dedup rules."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class ProductRepository:
    """Async repository for Product persistence.

    Dedup rules (used by upsert):
      1. If *url* is provided → match by url
      2. Otherwise → match by name + platform
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create(self, product: Product) -> Product:
        """Insert a new product and return it."""
        self._session.add(product)
        await self._session.flush()
        return product

    # ── Update ────────────────────────────────────────────────

    async def update(self, product: Product, **kwargs: object) -> Product:
        """Update an existing product with *kwargs* and return it."""
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        await self._session.flush()
        return product

    # ── Upsert ────────────────────────────────────────────────

    async def upsert(self, **kwargs: object) -> tuple[Product, bool]:
        """Insert or update a product based on dedup rules.

        Returns:
            (product, is_new) — *is_new* is True when a new row was created.
        """
        existing = await self._find_existing(
            url=kwargs.get("url"),
            name=kwargs.get("name"),
            platform=kwargs.get("platform"),
        )

        if existing is not None:
            await self.update(existing, **kwargs)
            return existing, False

        product = Product(**kwargs)  # type: ignore[arg-type]
        await self.create(product)
        return product, True

    # ── Internal ──────────────────────────────────────────────

    async def _find_existing(
        self,
        url: object,
        name: object,
        platform: object,
    ) -> Product | None:
        """Find an existing product by dedup rules.

        Priority:
          1. If *url* is provided → match by url ONLY (no fallback)
          2. If *url* is absent → match by *name* + *platform*
        """
        # 优先: url — 有 url 时只按 url 匹配, 不降级
        if url and isinstance(url, str):
            stmt = select(Product).where(Product.url == url)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()

        # 备选: name + platform (仅当无 url 时)
        if name and platform:
            stmt = select(Product).where(
                Product.name == name,
                Product.platform == platform,
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()

        return None
