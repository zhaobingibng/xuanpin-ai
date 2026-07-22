"""ShopRepository — high-level shop management with status-based operations.

Provides status-aware shop CRUD operations for the crawl pipeline:
- ACTIVE shops are eligible for crawling
- PAUSED shops are temporarily skipped
- DISABLED shops are permanently excluded
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shop_registry import ShopRegistry, ShopStatus


class ShopRepository:
    """Shop repository with status-based operations.

    Usage::

        repo = ShopRepository(session)
        shop = await repo.create_shop(
            platform="taobao",
            shop_id="shop123",
            shop_name="某某旗舰店",
            shop_url="https://shop123.taobao.com",
        )
        active_shops = await repo.list_active_shops()
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ─────────────────────────────────────────────────

    async def create_shop(
        self,
        platform: str,
        shop_id: str,
        shop_name: str,
        shop_url: str | None = None,
        category: str | None = None,
        priority: int = 1,
        status: ShopStatus = ShopStatus.ACTIVE,
    ) -> ShopRegistry:
        """Create a new shop.

        Args:
            platform: Platform name (taobao/tmall).
            shop_id: Unique shop identifier on the platform.
            shop_name: Display name of the shop.
            shop_url: Shop homepage URL.
            category: Product category.
            priority: Crawl priority (1=low, 2=medium, 3=high).
            status: Initial shop status.

        Returns:
            Created ShopRegistry instance.
        """
        shop = ShopRegistry(
            platform=platform,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_url=shop_url,
            category=category,
            priority=priority,
            status=status.value,
            enabled=(status == ShopStatus.ACTIVE),
        )
        self._session.add(shop)
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info(
            "[ShopRepository] Created shop: id={}, name='{}', status={}",
            shop.id, shop_name, status.value,
        )
        return shop

    # ── Read ───────────────────────────────────────────────────

    async def get_shop_by_id(self, shop_id: int) -> ShopRegistry | None:
        """Get shop by primary key.

        Args:
            shop_id: Shop primary key ID.

        Returns:
            ShopRegistry or None if not found.
        """
        return await self._session.get(ShopRegistry, shop_id)

    async def get_shop_by_platform_id(
        self, platform: str, shop_id: str
    ) -> ShopRegistry | None:
        """Get shop by platform + shop_id.

        Args:
            platform: Platform name.
            shop_id: Platform-specific shop identifier.

        Returns:
            ShopRegistry or None if not found.
        """
        stmt = select(ShopRegistry).where(
            ShopRegistry.platform == platform,
            ShopRegistry.shop_id == shop_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_shops(
        self, platform: str | None = None
    ) -> list[ShopRegistry]:
        """Get all ACTIVE shops, optionally filtered by platform.

        Args:
            platform: Optional platform filter.

        Returns:
            List of active ShopRegistry instances, ordered by priority.
        """
        stmt = select(ShopRegistry).where(
            ShopRegistry.status == ShopStatus.ACTIVE.value,
            ShopRegistry.enabled.is_(True),
        )
        if platform:
            stmt = stmt.where(ShopRegistry.platform == platform)
        stmt = stmt.order_by(ShopRegistry.priority.desc(), ShopRegistry.shop_name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_shops(self) -> list[ShopRegistry]:
        """Get all shops regardless of status."""
        stmt = select(ShopRegistry).order_by(ShopRegistry.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Update ─────────────────────────────────────────────────

    async def update_crawl_status(
        self,
        shop_id: int,
        success: bool,
        crawl_time: datetime | None = None,
    ) -> ShopRegistry | None:
        """Update shop crawl status after a crawl attempt.

        Args:
            shop_id: Shop primary key ID.
            success: Whether the crawl was successful.
            crawl_time: Time of the crawl (defaults to now).

        Returns:
            Updated ShopRegistry or None if not found.
        """
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return None

        now = crawl_time or datetime.now()
        shop.last_crawl_time = now

        if success:
            shop.last_success_time = now

        await self._session.commit()
        await self._session.refresh(shop)
        logger.info(
            "[ShopRepository] Updated crawl status: id={}, success={}",
            shop_id, success,
        )
        return shop

    async def pause_shop(self, shop_id: int) -> ShopRegistry | None:
        """Pause a shop (temporarily stop crawling).

        Args:
            shop_id: Shop primary key ID.

        Returns:
            Updated ShopRegistry or None if not found.
        """
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return None

        shop.status = ShopStatus.PAUSED.value
        shop.enabled = False
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info("[ShopRepository] Paused shop: id={}", shop_id)
        return shop

    async def activate_shop(self, shop_id: int) -> ShopRegistry | None:
        """Activate a shop (resume crawling).

        Args:
            shop_id: Shop primary key ID.

        Returns:
            Updated ShopRegistry or None if not found.
        """
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return None

        shop.status = ShopStatus.ACTIVE.value
        shop.enabled = True
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info("[ShopRepository] Activated shop: id={}", shop_id)
        return shop

    async def disable_shop(self, shop_id: int) -> ShopRegistry | None:
        """Permanently disable a shop.

        Args:
            shop_id: Shop primary key ID.

        Returns:
            Updated ShopRegistry or None if not found.
        """
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return None

        shop.status = ShopStatus.DISABLED.value
        shop.enabled = False
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info("[ShopRepository] Disabled shop: id={}", shop_id)
        return shop

    # ── Crawl Pipeline Integration ─────────────────────────────

    async def get_shops_for_crawl(
        self, platform: str | None = None
    ) -> list[ShopRegistry]:
        """Get shops ready for crawling.

        Returns ACTIVE shops that are enabled, ordered by priority.
        This is the main entry point for the crawl pipeline.

        Args:
            platform: Optional platform filter.

        Returns:
            List of shops ready for crawling.
        """
        return await self.list_active_shops(platform)
