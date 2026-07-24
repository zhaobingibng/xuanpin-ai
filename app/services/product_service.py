"""Async CRUD service for Product."""

from __future__ import annotations

from typing import Any, Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.models.schemas import RawProduct
from app.database.history_repository import HistoryRepository
from app.database.product_repository import ProductRepository
from app.models.product import Product
from app.services.cleaner.pipeline import ProductCleanPipeline
from app.services.product_scoring import ProductScoringService


class ProductService:
    """Provides async CRUD operations for Product entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ProductRepository(session)
        self._history_repo = HistoryRepository(session)
        self._pipeline = ProductCleanPipeline()
        self._scoring = ProductScoringService()

    # ── Ingestion ─────────────────────────────────────────────

    async def save_raw_products(
        self, products: list[RawProduct]
    ) -> dict[str, Any]:
        """Clean raw products and persist them to the database.

        Flow: RawProduct → CleanPipeline → Repository.upsert → DB.

        Returns:
            Dict with detailed stats and saved products:
            {"total": int, "cleaned_count": int, "saved_count": int,
             "new_count": int, "updated_count": int, "history_count": int,
             "failed_count": int, "saved_products": list[Product]}
        """
        total = len(products)
        logger.info("开始保存商品: 输入数量={}", total)

        empty_result: dict[str, Any] = {
            "total": total, "cleaned_count": 0, "saved_count": 0,
            "new_count": 0, "updated_count": 0, "history_count": 0,
            "failed_count": 0, "saved_products": [],
        }
        if total == 0:
            return empty_result

        # Step 1: clean + classify + batch-dedup
        cleaned = self._pipeline.process_batch(products)
        cleaned_count = len(cleaned)
        logger.info("清洗完成: 清洗数量={}", cleaned_count)

        if cleaned_count == 0:
            return empty_result

        # Step 2: upsert each cleaned product + history snapshot
        new_count = 0
        updated_count = 0
        failed_count = 0
        history_count = 0
        saved_products: list[Product] = []

        for item in cleaned:
            try:
                kwargs = item.to_db_kwargs()
                product, is_new = await self._repo.upsert(**kwargs)
                # 集中化写入 AI 评分：复用 ProductScoringService，确保所有采集入库路径
                # 都持久化 Product.ai_score（此前仅个别 caller 手动写入，导致大量商品为空）。
                product.ai_score = self._scoring.calculate_score(product)["total_score"]
                if is_new:
                    new_count += 1
                else:
                    updated_count += 1
                saved_products.append(product)

                # Step 3: create history snapshot
                snapshot = await self._history_repo.create_snapshot(product)
                if snapshot is not None:
                    history_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning("保存商品失败: {}", e)

        try:
            await self._session.commit()
            # Refresh products to get DB-generated IDs
            for p in saved_products:
                await self._session.refresh(p)
        except Exception as e:
            logger.error("提交失败: {}", e)
            await self._session.rollback()
            return {
                "total": total, "cleaned_count": cleaned_count, "saved_count": 0,
                "new_count": 0, "updated_count": 0, "history_count": 0,
                "failed_count": cleaned_count, "saved_products": [],
            }

        saved_count = new_count + updated_count
        logger.info(
            "保存完成: 新增={}, 更新={}, 历史={}, 失败={}",
            new_count, updated_count, history_count, failed_count,
        )
        return {
            "total": total,
            "cleaned_count": cleaned_count,
            "saved_count": saved_count,
            "new_count": new_count,
            "updated_count": updated_count,
            "history_count": history_count,
            "failed_count": failed_count,
            "saved_products": saved_products,
        }

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
        status: str | None = "ACTIVE",
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Product]:
        """List products with optional filters and pagination.

        Args:
            platform: 平台筛选。
            shop: 店铺筛选。
            status: 状态筛选，默认 "ACTIVE"，None 表示不过滤。
            limit: 分页大小。
            offset: 分页偏移。
        """
        stmt = select(Product)
        if status is not None:
            stmt = stmt.where(Product.status == status)
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
