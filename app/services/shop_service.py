"""ShopService — shop registry CRUD operations."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shop_registry import ShopRegistry


class ShopService:
    """店铺注册表服务。

    Usage::

        svc = ShopService(session)
        shop = await svc.create_shop(
            platform="taobao",
            shop_id="shop123",
            shop_name="某某旗舰店",
        )
        enabled = await svc.list_enabled_shops()
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
        fans: int = 0,
        priority: int = 1,
        enabled: bool = True,
        monitor_strategy: str = "daily",
    ) -> ShopRegistry:
        """创建店铺记录。"""
        shop = ShopRegistry(
            platform=platform,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_url=shop_url,
            category=category,
            fans=fans,
            priority=priority,
            enabled=enabled,
            monitor_strategy=monitor_strategy,
        )
        self._session.add(shop)
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info("[ShopService] Created shop: id={}, name='{}', platform='{}'", shop.id, shop_name, platform)
        return shop

    # ── Update ─────────────────────────────────────────────────

    async def update_shop(self, shop_id: int, **kwargs: object) -> ShopRegistry | None:
        """更新店铺信息。只更新传入的非 None 字段。"""
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(shop, key):
                setattr(shop, key, value)
        await self._session.commit()
        await self._session.refresh(shop)
        logger.info("[ShopService] Updated shop: id={}", shop_id)
        return shop

    # ── Delete ─────────────────────────────────────────────────

    async def delete_shop(self, shop_id: int) -> bool:
        """删除店铺记录。返回是否删除成功。"""
        shop = await self._session.get(ShopRegistry, shop_id)
        if shop is None:
            return False
        await self._session.delete(shop)
        await self._session.commit()
        logger.info("[ShopService] Deleted shop: id={}", shop_id)
        return True

    # ── Query ──────────────────────────────────────────────────

    async def list_enabled_shops(self, platform: str | None = None) -> list[ShopRegistry]:
        """获取所有启用的店铺。可按平台过滤。"""
        stmt = select(ShopRegistry).where(ShopRegistry.enabled.is_(True))
        if platform:
            stmt = stmt.where(ShopRegistry.platform == platform)
        stmt = stmt.order_by(ShopRegistry.priority.desc(), ShopRegistry.shop_name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_shops(self) -> list[ShopRegistry]:
        """获取全部店铺（含禁用）。"""
        stmt = select(ShopRegistry).order_by(ShopRegistry.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_shop_id(self, platform: str, shop_id: str) -> ShopRegistry | None:
        """按平台 + shop_id 查找。"""
        stmt = select(ShopRegistry).where(
            ShopRegistry.platform == platform,
            ShopRegistry.shop_id == shop_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_shop(self, shop_id: int) -> ShopRegistry | None:
        """按主键获取。"""
        return await self._session.get(ShopRegistry, shop_id)

    # ── Mark scanned ──────────────────────────────────────────

    async def mark_scanned(self, shop_id: int, scan_time: datetime | None = None) -> ShopRegistry | None:
        """标记店铺已扫描。"""
        if scan_time is None:
            scan_time = datetime.now()
        stmt = (
            update(ShopRegistry)
            .where(ShopRegistry.id == shop_id)
            .values(last_scan_at=scan_time)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return await self._session.get(ShopRegistry, shop_id)

    async def batch_mark_scanned(
        self, shop_ids: list[int], scan_time: datetime | None = None
    ) -> int:
        """批量标记店铺已扫描。返回更新数量。"""
        if not shop_ids:
            return 0
        if scan_time is None:
            scan_time = datetime.now()
        stmt = (
            update(ShopRegistry)
            .where(ShopRegistry.id.in_(shop_ids))
            .values(last_scan_at=scan_time)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        logger.info("[ShopService] Batch marked {} shops as scanned", result.rowcount)
        return result.rowcount

    async def register_or_update(
        self,
        platform: str,
        shop_id: str,
        shop_name: str,
        shop_url: str | None = None,
        category: str | None = None,
        fans: int = 0,
        priority: int = 1,
        enabled: bool = True,
        monitor_strategy: str = "daily",
    ) -> ShopRegistry:
        """Upsert: 如果 platform+shop_id 已存在则更新，否则创建。"""
        existing = await self.find_by_shop_id(platform, shop_id)
        if existing:
            # Update existing
            existing.shop_name = shop_name
            if shop_url is not None:
                existing.shop_url = shop_url
            if category is not None:
                existing.category = category
            if fans:
                existing.fans = fans
            existing.priority = priority
            existing.enabled = enabled
            existing.monitor_strategy = monitor_strategy
            await self._session.commit()
            await self._session.refresh(existing)
            logger.info("[ShopService] Updated existing shop: platform={}, shop_id={}", platform, shop_id)
            return existing
        else:
            return await self.create_shop(
                platform=platform,
                shop_id=shop_id,
                shop_name=shop_name,
                shop_url=shop_url,
                category=category,
                fans=fans,
                priority=priority,
                enabled=enabled,
                monitor_strategy=monitor_strategy,
            )

    async def get_shops_needing_scan(
        self, platform: str | None = None
    ) -> list[ShopRegistry]:
        """获取需要扫描的店铺（基于监控策略和上次扫描时间）。"""
        now = datetime.now()
        stmt = select(ShopRegistry).where(ShopRegistry.enabled.is_(True))
        if platform:
            stmt = stmt.where(ShopRegistry.platform == platform)

        query_result = await self._session.execute(stmt)
        all_shops = list(query_result.scalars().all())

        needing_scan = []
        for shop in all_shops:
            strategy = shop.monitor_strategy

            # manual shops never auto-scan
            if strategy == "manual":
                continue

            last_scan = shop.last_scan_at

            if last_scan is None:
                needing_scan.append(shop)
                continue

            # Calculate threshold based on strategy
            if strategy == "hourly":
                threshold = now - timedelta(hours=1)
            elif strategy == "daily":
                threshold = now - timedelta(days=1)
            else:
                threshold = now - timedelta(days=1)  # default daily

            if last_scan < threshold:
                needing_scan.append(shop)

        return needing_scan

    async def get_shop_stats(self) -> dict:
        """获取店铺统计信息。"""
        all_shops = await self.list_all_shops()
        enabled = [s for s in all_shops if s.enabled]
        by_platform: dict[str, int] = {}
        for s in all_shops:
            by_platform[s.platform] = by_platform.get(s.platform, 0) + 1
        return {
            "total": len(all_shops),
            "enabled": len(enabled),
            "by_platform": by_platform,
        }
