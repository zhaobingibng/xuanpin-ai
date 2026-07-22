"""ProductMatcher — match Taobao titles against 1688 supplier products.

Uses TextMatcher + FeatureExtractor + FusionMatcher (+ ImageMatcher) for multi-dimensional scoring.

支持多模态匹配（Phase 33）：
    - 纯文本：         match_product(title, top_k=10)
    - 文本+图片：      match_product(title, image=..., top_k=10)

支持向量召回加速（Phase 34）：
    - recall_first=True（默认）：RecallEngine → 候选过滤 → 精排
    - recall_first=False：全表扫描 → 精排（旧行为）
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.text_matcher import TextMatcher
from app.matching.feature_extractor import FeatureExtractor
from app.matching.fusion_matcher import FusionMatcher
from app.models.supplier_product import SupplierProductDB

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from app.matching.recall_engine import RecallEngine


class ProductMatcher:
    """Product matching engine for Taobao-to-1688 matching.

    Matches a product title (and optionally image) against all supplier
    products in the database, returning the top-K most similar matches
    with fusion scoring.

    Two-stage pipeline (default):
        ┌─ title → RecallEngine (vector recall, top_k*10 candidates)
        │        → TextMatcher (text_score)
        │        → FeatureExtractor (query_features, candidate_features)
        │        → ImageMatcher (image_score, if image provided)
        │        → FusionMatcher (final_score)
        └─ sort by final_score desc → top_k results

    Full-scan pipeline (recall_first=False):
        ┌─ title → load all products
        │        → TextMatcher (text_score)
        │        → FeatureExtractor (query_features, candidate_features)
        │        → ImageMatcher (image_score, if image provided)
        │        → FusionMatcher (final_score)
        └─ sort by final_score desc

    Pure text (backward compatible):
        final_score = text*0.6 + feature*0.4

    Multimodal (with image):
        final_score = text*0.4 + feature*0.3 + image*0.3

    Usage:
        matcher = ProductMatcher(session)

        # 默认：向量召回加速
        results = await matcher.match_product("三只松鼠坚果礼盒装", top_k=10)

        # 全表扫描（兼容旧行为）
        results = await matcher.match_product("坚果礼盒", top_k=10, recall_first=False)

        # 多模态匹配
        results = await matcher.match_product("坚果礼盒", image=img, top_k=10)
    """

    def __init__(
        self,
        session: AsyncSession,
        text_matcher: TextMatcher | None = None,
        feature_extractor: FeatureExtractor | None = None,
        fusion_matcher: FusionMatcher | None = None,
        recall_first: bool = True,
    ) -> None:
        """Initialize ProductMatcher.

        Args:
            session: Async database session.
            text_matcher: Optional TextMatcher instance. Creates default if None.
            feature_extractor: Optional FeatureExtractor instance.
            fusion_matcher: Optional FusionMatcher instance.
            recall_first: If True (default), use RecallEngine for fast
                candidate retrieval before fine scoring. If False, scan
                all products (old behavior).
        """
        self._session = session
        self._text_matcher = text_matcher or TextMatcher()
        self._feature_extractor = feature_extractor or FeatureExtractor()
        self._fusion_matcher = fusion_matcher or FusionMatcher(
            extractor=self._feature_extractor
        )
        self._image_matcher = None  # lazy init
        self._recall_engine: RecallEngine | None = None  # lazy init
        self._recall_first = recall_first

    async def match_product(
        self,
        title: str,
        image: "str | Path | PILImage | bytes | None" = None,
        top_k: int = 10,
        recall_first: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Match a product title (and optionally image) against supplier products.

        Args:
            title: Product title to match (e.g., Taobao product title).
            image: Optional query product image, supports:
                - PIL Image object
                - Local file path (str / Path)
                - Image URL (http/https)
                - bytes data
                When None → pure text matching (backward compatible).
            top_k: Number of top results to return.
            recall_first: Override the instance-level recall_first setting.
                None → use instance default.

        Returns:
            List of match results, each containing:
            - supplier_product_id: Database ID of the supplier product
            - similarity_score: Final fusion score [0, 1] (backward compat)
            - text_score: Pure text similarity score [0, 1]
            - feature_score: Feature-based similarity score [0, 1]
            - image_score: Image similarity score [0, 1] or None
            - final_score: Combined fusion score [0, 1]
            - title: Supplier product title
            - price: Supplier product price
            - url: Supplier product URL
            - offer_id: 1688 offer ID
            - shop_name: Supplier shop name
            - image: Product image URL
        """
        if not title or not title.strip():
            return []

        # Determine recall mode
        use_recall = recall_first if recall_first is not None else self._recall_first

        # Stage 1: Load candidates (vector recall or full scan)
        if use_recall:
            # Vector recall: get candidate IDs, then load only those products
            candidate_ids = await self._recall_candidates(title, top_k * 10)
            if not candidate_ids:
                return []
            products = await self._load_products_by_ids(candidate_ids)
            if not products:
                return []
            # Preserve recall order by sorting products to match recall ranking
            id_to_product = {p.id: p for p in products}
            products = [id_to_product[pid] for pid in candidate_ids if pid in id_to_product]
        else:
            products = await self._load_all_products()
            if not products:
                return []

        # Lazy-init ImageMatcher if image is provided
        has_image = image is not None
        if has_image and self._image_matcher is None:
            from app.matching.image_matcher import ImageMatcher
            self._image_matcher = ImageMatcher()

        # Extract features for query title
        query_features = self._feature_extractor.extract(title)

        # Calculate text similarities
        candidate_titles = [p.title for p in products]
        text_scored = self._text_matcher.calculate_similarity_batch(
            title, candidate_titles
        )

        # Create index lookup for text scores
        text_score_map: dict[int, float] = {}
        for idx, score in text_scored:
            text_score_map[idx] = score

        # Calculate fusion scores (with optional image matching)
        scored_results: list[tuple[int, float, float, float | None, float]] = []
        for idx, product in enumerate(products):
            text_score = text_score_map.get(idx, 0.0)

            # Skip zero text scores early
            if text_score <= 0:
                continue

            # Extract candidate features
            candidate_features = self._feature_extractor.extract(product.title)

            # Compute image score if query image is provided
            img_score: float | None = None
            if has_image and product.image and self._image_matcher:
                try:
                    img_score = self._image_matcher.calculate_similarity(
                        image, product.image
                    )
                except Exception as exc:
                    logger.debug(
                        "[ProductMatcher] Image matching failed for '{}': {}",
                        product.title[:30], exc,
                    )
                    img_score = None  # graceful degradation

            # Fusion score
            fusion_result = self._fusion_matcher.calculate(
                text_score=text_score,
                query_features=query_features,
                candidate_features=candidate_features,
                image_score=img_score,
            )

            scored_results.append((
                idx,
                fusion_result["text_score"],
                fusion_result["feature_score"],
                fusion_result.get("image_score"),
                fusion_result["final_score"],
            ))

        # Sort by final_score descending
        scored_results.sort(key=lambda x: x[4], reverse=True)

        # Build results (top_k, exclude zero final_score)
        results: list[dict[str, Any]] = []
        for idx, text_score, feature_score, img_score, final_score in scored_results[:top_k]:
            if final_score <= 0:
                continue
            product = products[idx]
            result: dict[str, Any] = {
                "supplier_product_id": product.id,
                "similarity_score": round(final_score, 4),
                "text_score": round(text_score, 4),
                "feature_score": round(feature_score, 4),
                "image_score": round(img_score, 4) if img_score is not None else None,
                "final_score": round(final_score, 4),
                "title": product.title,
                "price": product.price,
                "url": product.url,
                "offer_id": product.offer_id,
                "shop_name": product.shop_name,
                "image": product.image,
            }
            results.append(result)

        return results

    # ── Candidate recall (Phase 34) ───────────────────────────

    async def _recall_candidates(self, title: str, top_k: int) -> list[int]:
        """Recall candidate supplier_product_ids using vector similarity.

        Lazy-initializes RecallEngine on first call.
        """
        if self._recall_engine is None:
            from app.matching.recall_engine import RecallEngine
            self._recall_engine = RecallEngine(self._session)
            await self._recall_engine.build_index()
        return await self._recall_engine.recall(title, top_k=top_k)

    # ── DB access ─────────────────────────────────────────────

    async def _load_all_products(self) -> Sequence[SupplierProductDB]:
        """Load all supplier products from database.

        Returns:
            List of SupplierProductDB records.
        """
        stmt = select(SupplierProductDB).where(
            SupplierProductDB.title != ""
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def _load_products_by_ids(
        self, ids: list[int],
    ) -> Sequence[SupplierProductDB]:
        """Load specific supplier products by their IDs.

        Args:
            ids: List of supplier_product IDs to load.

        Returns:
            List of SupplierProductDB records.
        """
        if not ids:
            return []
        stmt = select(SupplierProductDB).where(
            SupplierProductDB.id.in_(ids),
            SupplierProductDB.title != "",
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
