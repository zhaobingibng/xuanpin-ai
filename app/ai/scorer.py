"""Product AI scorer — applies rules engine to compute ai_score (0-100)."""

from __future__ import annotations

from loguru import logger

from app.ai.rules import calculate_score, score_price, score_sales, score_viewers
from app.crawler.models.schemas import RawProduct
from app.services.cleaner.pipeline import CleanedProduct


class ProductScorer:
    """Compute ai_score for products using the rules engine.

    Works with both CleanedProduct (from pipeline) and raw dict/kwargs.
    """

    # ── Single product scoring ────────────────────────────────

    def score(
        self,
        *,
        sales_24h: int = 0,
        viewers: int = 0,
        price: float = 0.0,
    ) -> float:
        """Calculate ai_score (0-100) from raw metrics.

        Returns a float rounded to 2 decimal places.
        """
        return calculate_score(
            sales=sales_24h,
            viewers=viewers,
            price=price,
        )

    def score_product(self, product: CleanedProduct) -> float:
        """Score a CleanedProduct and return ai_score."""
        score = self.score(
            sales_24h=product.sales_24h,
            viewers=product.viewers,
            price=product.price,
        )
        logger.debug(
            "Scored '{}': {:.1f} (sales={}, viewers={}, price={})",
            product.name, score, product.sales_24h, product.viewers, product.price,
        )
        return score

    # ── Dimension breakdown ───────────────────────────────────

    def breakdown(
        self,
        *,
        sales_24h: int = 0,
        viewers: int = 0,
        price: float = 0.0,
    ) -> dict[str, float]:
        """Return per-dimension scores (useful for debugging / display).

        Returns dict with keys: sales, viewers, price, total.
        """
        s = score_sales(sales_24h)
        v = score_viewers(viewers)
        p = score_price(price)
        total = calculate_score(sales_24h, viewers, price)
        return {
            "sales": s,
            "viewers": v,
            "price": p,
            "total": total,
        }
