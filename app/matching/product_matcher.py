"""ProductMatcher — match Taobao titles against 1688 supplier products.

Uses TextMatcher + FeatureExtractor + FusionMatcher for multi-dimensional scoring.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.text_matcher import TextMatcher
from app.matching.feature_extractor import FeatureExtractor
from app.matching.fusion_matcher import FusionMatcher
from app.models.supplier_product import SupplierProductDB


class ProductMatcher:
    """Product matching engine for Taobao-to-1688 matching.
    
    Matches a product title against all supplier products in the database,
    returning the top-K most similar matches with fusion scoring.
    
    Scoring pipeline:
        title → TextMatcher (text_score)
             → FeatureExtractor (query_features, candidate_features)
             → FusionMatcher (final_score = text*0.6 + feature*0.4)
             → sort by final_score desc

    Usage:
        matcher = ProductMatcher(session)
        results = await matcher.match_product("三只松鼠坚果礼盒装", top_k=10)
    """

    def __init__(
        self,
        session: AsyncSession,
        text_matcher: TextMatcher | None = None,
        feature_extractor: FeatureExtractor | None = None,
        fusion_matcher: FusionMatcher | None = None,
    ) -> None:
        """Initialize ProductMatcher.
        
        Args:
            session: Async database session.
            text_matcher: Optional TextMatcher instance. Creates default if None.
            feature_extractor: Optional FeatureExtractor instance.
            fusion_matcher: Optional FusionMatcher instance.
        """
        self._session = session
        self._text_matcher = text_matcher or TextMatcher()
        self._feature_extractor = feature_extractor or FeatureExtractor()
        self._fusion_matcher = fusion_matcher or FusionMatcher(
            extractor=self._feature_extractor
        )

    async def match_product(
        self, title: str, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Match a product title against supplier products.
        
        Args:
            title: Product title to match (e.g., Taobao product title).
            top_k: Number of top results to return.
        
        Returns:
            List of match results, each containing:
            - supplier_product_id: Database ID of the supplier product
            - similarity_score: Final fusion score [0, 1] (backward compat)
            - text_score: Pure text similarity score [0, 1]
            - feature_score: Feature-based similarity score [0, 1]
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
        
        # Load all supplier products
        products = await self._load_all_products()
        if not products:
            return []
        
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
        
        # Calculate fusion scores
        scored_results: list[tuple[int, float, float, float]] = []
        for idx, product in enumerate(products):
            text_score = text_score_map.get(idx, 0.0)
            
            # Skip zero text scores early
            if text_score <= 0:
                continue
            
            # Extract candidate features
            candidate_features = self._feature_extractor.extract(product.title)
            
            # Fusion score
            fusion_result = self._fusion_matcher.calculate(
                text_score=text_score,
                query_features=query_features,
                candidate_features=candidate_features,
            )
            
            scored_results.append((
                idx,
                fusion_result["text_score"],
                fusion_result["feature_score"],
                fusion_result["final_score"],
            ))
        
        # Sort by final_score descending
        scored_results.sort(key=lambda x: x[3], reverse=True)
        
        # Build results (top_k, exclude zero final_score)
        results: list[dict[str, Any]] = []
        for idx, text_score, feature_score, final_score in scored_results[:top_k]:
            if final_score <= 0:
                continue
            product = products[idx]
            results.append({
                "supplier_product_id": product.id,
                "similarity_score": round(final_score, 4),
                "text_score": round(text_score, 4),
                "feature_score": round(feature_score, 4),
                "final_score": round(final_score, 4),
                "title": product.title,
                "price": product.price,
                "url": product.url,
                "offer_id": product.offer_id,
                "shop_name": product.shop_name,
                "image": product.image,
            })
        
        return results

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
