"""Async CRUD service for Product."""

from __future__ import annotations

from typing import Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.models.schemas import RawProduct
from app.database.history_repository import HistoryRepository
from app.database.product_repository import ProductRepository
from app.models.product import Product
from app.services.cleaner.pipeline import ProductCleanPipeline


class ProductService:
    """Provides async CRUD operations for Product entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ProductRepository(session)
        self._history_repo = HistoryRepository(session)
        self._pipeline = ProductCleanPipeline()

    # ── Ingestion ─────────────────────────────────────────────

    async def save_raw_products(
        self, products: list[RawProduct]
    ) -> int:
        """Clean raw products and persist them to the database.

        Flow: RawProduct → CleanPipeline → Repository.upsert → DB.

        Returns:
            The number of products successfully saved (new + updated).
        """
        total = len(products)
        logger.info("开始保存商品: 输入数量={}", total)

        if total == 0:
            return 0

        # Step 1: clean + classify + batch-dedup
        cleaned = self._pipeline.process_batch(products)
        cleaned_count = len(cleaned)
        logger.info("清洗完成: 清洗数量={}", cleaned_count)

        # Step 2: upsert each cleaned product + history snapshot
        new_count = 0
        updated_count = 0
        failed_count = 0
        history_count = 0

        for item in cleaned:
            try:
                kwargs = item.to_db_kwargs()
                product, is_new = await self._repo.upsert(**kwargs)
                if is_new:
                    new_count += 1
                else:
                    updated_count += 1

                # Step 3: create history snapshot
                snapshot = await self._history_repo.create_snapshot(product)
                if snapshot is not None:
                    history_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning("保存商品失败: {}", e)

        await self._session.commit()

        logger.info(
            "保存完成: 新增={}, 更新={}, 历史={}, 失败={}",
            new_count,
            updated_count,
            history_count,
            failed_count,
        )
        return new_count + updated_count

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
