"""NewProductDetector — detect newly listed products from monitored shops."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.shop_registry import ShopRegistry


class NewProductDetector:
    """检测监控店铺的新上架商品。

    通过对比 ShopRegistry.last_scan_at 时间与商品 created_at 时间，
    识别在该时间窗口内首次出现的商品。

    Usage::

        detector = NewProductDetector(session)
        result = await detector.detect_shop_new_products(shop_registry_id=1)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def detect_shop_new_products(
        self,
        shop_registry_id: int,
    ) -> dict[str, Any]:
        """检测指定店铺的新上架商品。

        Args:
            shop_registry_id: ShopRegistry 表的主键 ID。

        Returns:
            包含检测结果字典:
            {
                "shop_id": int,
                "shop_name": str,
                "new_products": list[Product],
                "new_count": int,
                "scan_time": datetime,
            }
        """
        # 1. 获取店铺信息
        shop = await self._session.get(ShopRegistry, shop_registry_id)
        if shop is None:
            logger.warning("[NewProductDetector] 店铺不存在: id={}", shop_registry_id)
            return {
                "shop_id": shop_registry_id,
                "shop_name": "",
                "new_products": [],
                "new_count": 0,
                "scan_time": datetime.now(),
            }

        last_scan = shop.last_scan_at
        scan_time = datetime.now()

        # 2. 查询该店铺在 last_scan_at 之后创建的商品
        stmt = select(Product).where(
            Product.platform == shop.platform,
            Product.shop == shop.shop_name,
            Product.status == "ACTIVE",
        )
        if last_scan is not None:
            stmt = stmt.where(Product.created_at > last_scan)

        result = await self._session.execute(stmt)
        new_products = list(result.scalars().all())

        # 3. 更新 last_scan_at
        shop.last_scan_at = scan_time
        await self._session.commit()

        logger.info(
            "[NewProductDetector] 店铺 '{}' 新品检测完成: 新增 {} 个商品 (last_scan={})",
            shop.shop_name,
            len(new_products),
            last_scan.isoformat() if last_scan else "None",
        )

        return {
            "shop_id": shop_registry_id,
            "shop_name": shop.shop_name,
            "new_products": new_products,
            "new_count": len(new_products),
            "scan_time": scan_time,
        }

    async def detect_all_enabled_shops(
        self,
        platform: str | None = None,
    ) -> dict[str, Any]:
        """检测所有启用监控店铺的新品。

        Args:
            platform: 可选平台过滤。

        Returns:
            汇总结果字典。
        """
        # 查询启用的店铺
        stmt = select(ShopRegistry).where(ShopRegistry.enabled.is_(True))
        if platform:
            stmt = stmt.where(ShopRegistry.platform == platform)
        stmt = stmt.order_by(ShopRegistry.priority.desc())

        result = await self._session.execute(stmt)
        shops = list(result.scalars().all())

        all_new_products: list[Product] = []
        shop_results: list[dict[str, Any]] = []

        for shop in shops:
            shop_result = await self.detect_shop_new_products(shop.id)
            shop_results.append({
                "shop_id": shop.id,
                "shop_name": shop_result["shop_name"],
                "new_count": shop_result["new_count"],
            })
            all_new_products.extend(shop_result["new_products"])

        logger.info(
            "[NewProductDetector] 全店新品检测完成: {} 个店铺, {} 个新品",
            len(shops),
            len(all_new_products),
        )

        return {
            "total_shops": len(shops),
            "total_new_products": len(all_new_products),
            "shop_results": shop_results,
            "new_products": all_new_products,
        }
