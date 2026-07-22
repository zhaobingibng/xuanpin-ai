"""RecallEngine — fast candidate retrieval using vector similarity (Phase 34).

Two-stage recall pipeline:
    product → EmbeddingService → VectorIndex → candidate IDs

Replaces full-table scan in ProductMatcher with fast vector-based
candidate retrieval for improved performance.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.embedding_service import EmbeddingService
from app.matching.vector_index import VectorIndex
from app.models.supplier_product import SupplierProductDB


class RecallEngine:
    """Two-stage recall engine for fast candidate retrieval.

    Builds a vector index from all supplier products and uses cosine
    similarity to quickly recall the top-k most similar candidates.

    Usage::

        engine = RecallEngine(session)
        await engine.build_index()
        candidates = await engine.recall(product, top_k=100)
        # [42, 7, 103, ...] — supplier_product_ids
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize RecallEngine.

        Args:
            session: Async database session for loading products.
            embedding_service: Optional EmbeddingService instance.
                Creates default (dim=512) if None.
        """
        self._session = session
        self._embedding = embedding_service or EmbeddingService()
        self._index = VectorIndex()
        self._built = False

    # ── Public API ────────────────────────────────────────────

    async def build_index(self) -> int:
        """Build vector index from all supplier products in DB.

        Loads all products with non-empty titles, encodes them into
        vectors, and adds to the index.

        Returns:
            Number of items indexed.
        """
        logger.info("[RecallEngine] Building vector index ...")

        stmt = select(SupplierProductDB).where(
            SupplierProductDB.title != ""
        )
        result = await self._session.execute(stmt)
        products = result.scalars().all()

        for product in products:
            vector = self._embedding.encode_product(product)
            self._index.add(product.id, vector)

        self._built = True
        logger.info(
            "[RecallEngine] Index built: {} items, dim={}",
            len(self._index), self._embedding.dim,
        )
        return len(self._index)

    async def recall(
        self,
        product: Any,
        top_k: int = 100,
    ) -> list[int]:
        """Recall candidate supplier_product_ids for a given product.

        Lazy-builds the index on first call if not already built.

        Args:
            product: Product with ``.name`` or ``.title`` attribute,
                or a plain title string.
            top_k: Maximum number of candidates to return.

        Returns:
            List of supplier_product_ids, sorted by similarity descending.
        """
        if not self._built:
            await self.build_index()

        # Extract title from product object or use string directly
        text = self._extract_title(product)

        if not text:
            return []

        vector = self._embedding.encode_text(text)
        results = self._index.search(vector, top_k=top_k)
        return [item_id for item_id, _ in results]

    # ── Info ──────────────────────────────────────────────────

    @property
    def index_size(self) -> int:
        """Number of items in the index."""
        return len(self._index)

    @property
    def is_built(self) -> bool:
        """Whether the index has been built."""
        return self._built

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _extract_title(product: Any) -> str:
        """Extract a title string from various product representations.

        Args:
            product: Can be a Product ORM, SupplierProductDB, plain str,
                or any object with ``.name`` or ``.title``.

        Returns:
            Title string, or empty string if not extractable.
        """
        if isinstance(product, str):
            return product
        # Prefer .name first, but skip empty values
        if hasattr(product, "name"):
            val = getattr(product, "name")
            if val:
                return str(val)
        if hasattr(product, "title"):
            val = getattr(product, "title")
            if val:
                return str(val)
        return str(product) if product else ""
