"""Product analyzer — batch scoring, ranking, and top-hits extraction."""

from __future__ import annotations

from loguru import logger

from app.ai.scorer import ProductScorer
from app.services.cleaner.pipeline import CleanedProduct


class ProductAnalyzer:
    """Batch analysis: score, rank, and filter products."""

    def __init__(self) -> None:
        self._scorer = ProductScorer()

    # ── Batch scoring ─────────────────────────────────────────

    def analyze(self, products: list[CleanedProduct]) -> list[dict]:
        """Score a list of CleanedProducts.

        Returns list of dicts, each containing:
            product: CleanedProduct
            ai_score: float
            breakdown: dict with per-dimension scores
        """
        results = []
        for product in products:
            breakdown = self._scorer.breakdown(
                sales_24h=product.sales_24h,
                viewers=product.viewers,
                price=product.price,
            )
            results.append({
                "product": product,
                "ai_score": breakdown["total"],
                "breakdown": breakdown,
            })
        logger.info("Analyzed {} products", len(results))
        return results

    # ── Ranking ───────────────────────────────────────────────

    def rank(self, products: list[CleanedProduct]) -> list[dict]:
        """Score and rank products by ai_score descending.

        Returns sorted list of analyze() result dicts.
        """
        results = self.analyze(products)
        results.sort(key=lambda r: r["ai_score"], reverse=True)
        return results

    # ── Top hits ──────────────────────────────────────────────

    def top_hits(
        self,
        products: list[CleanedProduct],
        n: int = 10,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Return top N products by ai_score, filtered by min_score.

        Args:
            products: list of CleanedProducts
            n: max number of results
            min_score: minimum ai_score threshold (0-100)
        """
        ranked = self.rank(products)
        filtered = [r for r in ranked if r["ai_score"] >= min_score]
        return filtered[:n]

    # ── Summary stats ─────────────────────────────────────────

    def summary(self, products: list[CleanedProduct]) -> dict:
        """Return summary statistics for a product batch.

        Returns dict with: count, avg_score, max_score, min_score, score_distribution.
        """
        if not products:
            return {
                "count": 0,
                "avg_score": 0.0,
                "max_score": 0.0,
                "min_score": 0.0,
                "score_distribution": {},
            }

        results = self.analyze(products)
        scores = [r["ai_score"] for r in results]

        # Distribution buckets: 0-20, 20-40, 40-60, 60-80, 80-100
        buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for s in scores:
            if s < 20:
                buckets["0-20"] += 1
            elif s < 40:
                buckets["20-40"] += 1
            elif s < 60:
                buckets["40-60"] += 1
            elif s < 80:
                buckets["60-80"] += 1
            else:
                buckets["80-100"] += 1

        return {
            "count": len(scores),
            "avg_score": round(sum(scores) / len(scores), 2),
            "max_score": max(scores),
            "min_score": min(scores),
            "score_distribution": buckets,
        }
