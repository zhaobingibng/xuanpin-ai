"""Product repository — create / update / upsert with dedup rules."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select, update
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

    # ── Save Product (with new product detection) ─────────────

    async def save_product(
        self,
        *,
        name: str,
        platform: str,
        shop: str,
        url: str | None = None,
        image: str | None = None,
        price: float = 0.0,
        **kwargs: object,
    ) -> tuple[Product, bool]:
        """Save a product with new product detection.

        - If product_url doesn't exist: create new product, mark as NEW
        - If product_url exists: update last_seen_time

        Returns:
            (product, is_new) — is_new is True when a new row was created.
        """
        now = datetime.now()

        # Check if product exists by URL
        existing = await self.get_product_by_url(url) if url else None

        if existing is not None:
            # Update existing product
            existing.last_seen_time = now
            existing.price = price
            if image:
                existing.image = image
            await self._session.flush()
            return existing, False

        # Create new product
        product = Product(
            name=name,
            platform=platform,
            shop=shop,
            url=url,
            image=image,
            price=price,
            first_seen_time=now,
            last_seen_time=now,
            lifecycle_stage="NEW",
            **kwargs,
        )
        self._session.add(product)
        await self._session.flush()
        logger.info("[ProductRepository] New product saved: {}", name[:40])
        return product, True

    # ── Query Methods ─────────────────────────────────────────

    async def get_product_by_url(self, url: str) -> Product | None:
        """Get product by URL.

        Args:
            url: Product URL.

        Returns:
            Product or None if not found.
        """
        if not url:
            return None
        stmt = select(Product).where(Product.url == url)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_products(
        self,
        days: int = 7,
        platform: str | None = None,
        limit: int = 100,
    ) -> list[Product]:
        """Get recently seen products.

        Args:
            days: Number of days to look back.
            platform: Optional platform filter.
            limit: Max results.

        Returns:
            List of products seen within the time range.
        """
        cutoff = datetime.now() - timedelta(days=days)
        stmt = select(Product).where(Product.last_seen_time >= cutoff)
        if platform:
            stmt = stmt.where(Product.platform == platform)
        stmt = stmt.order_by(Product.last_seen_time.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_new_products(
        self,
        limit: int = 100,
        platform: str | None = None,
    ) -> list[Product]:
        """Find products marked as NEW (not seen before).

        These are products that have lifecycle_stage='NEW',
        meaning they were just discovered and haven't been processed.

        Args:
            limit: Max results.
            platform: Optional platform filter.

        Returns:
            List of new products.
        """
        stmt = select(Product).where(Product.lifecycle_stage == "NEW")
        if platform:
            stmt = stmt.where(Product.platform == platform)
        stmt = stmt.order_by(Product.first_seen_time.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

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

    # ── Archive ────────────────────────────────────────────────

    async def archive_stale(self, days: int = 30) -> int:
        """将超过 N 天未更新的商品标记为 ARCHIVED。

        Args:
            days: 多少天未更新则归档，默认 30。

        Returns:
            被归档的商品数量。
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            update(Product)
            .where(
                Product.status == "ACTIVE",
                Product.updated_at < cutoff,
            )
            .values(status="ARCHIVED")
        )
        result = await self._session.execute(stmt)
        archived = result.rowcount
        if archived > 0:
            logger.info("[archive] 归档 {} 个超过 {} 天未更新的商品", archived, days)
        return archived

    async def list_active(
        self,
        *,
        platform: str | None = None,
        shop: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Product]:
        """获取所有 ACTIVE 状态的商品。"""
        stmt = select(Product).where(Product.status == "ACTIVE")
        if platform:
            stmt = stmt.where(Product.platform == platform)
        if shop:
            stmt = stmt.where(Product.shop == shop)
        stmt = stmt.order_by(Product.id).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
