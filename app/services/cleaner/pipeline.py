"""End-to-end cleaning pipeline: RawProduct → CleanedProduct."""

from __future__ import annotations

from dataclasses import dataclass
from loguru import logger

from app.crawler.models.schemas import RawProduct
from app.services.cleaner.normalizer import price_normalize, sales_normalize
from app.services.cleaner.product_cleaner import ProductCleaner


@dataclass
class CleanedProduct:
    """Cleaned product data ready for persistence."""

    name: str
    platform: str
    shop: str
    price: float
    viewers: int
    sales_24h: int
    category: str
    image: str | None = None
    url: str | None = None

    def to_db_kwargs(self) -> dict:
        """Return kwargs suitable for ProductService.create()."""
        return {
            "name": self.name,
            "platform": self.platform,
            "shop": self.shop,
            "image": self.image,
            "price": self.price,
            "viewers": self.viewers,
            "sales_24h": self.sales_24h,
            "category": self.category or None,
            "url": self.url,
        }


class ProductCleanPipeline:
    """Pipeline that chains normalizer + cleaner + dedup.

    Usage::

        pipeline = ProductCleanPipeline()
        results = pipeline.process_batch(raw_products)
    """

    def __init__(self) -> None:
        self._cleaner = ProductCleaner()

    # ── Single item ───────────────────────────────────────────

    def process(self, raw: RawProduct) -> CleanedProduct | None:
        """Process one RawProduct through the full pipeline.

        Returns None if the data is invalid (empty name / bad price).
        Does NOT check deduplication — use process_batch for that.
        """
        # 1. Clean name
        name = self._cleaner.clean_name(raw.name)
        if not name:
            logger.warning("Product dropped: empty name after cleaning (raw='{}')", raw.name)
            return None

        # 2. Normalize price
        price = price_normalize(raw.price)
        if price is None:
            logger.warning("Product dropped: invalid price '{}' for '{}'", raw.price, name)
            return None

        # 3. Normalize sales & viewers
        sales = sales_normalize(raw.sales_24h) or 0
        viewers = sales_normalize(raw.viewers) or 0

        # 4. Classify
        category = self._cleaner.classify(name)

        return CleanedProduct(
            name=name,
            platform=raw.platform,
            shop=raw.shop,
            price=price,
            viewers=viewers,
            sales_24h=sales,
            category=category,
            image=raw.image,
            url=raw.url,
        )

    # ── Batch ─────────────────────────────────────────────────

    def process_batch(self, raw_products: list[RawProduct]) -> list[CleanedProduct]:
        """Process a list of RawProducts: clean → classify → deduplicate."""
        results: list[CleanedProduct] = []
        self._cleaner.reset()

        for raw in raw_products:
            cleaned = self.process(raw)
            if cleaned is None:
                continue

            if self._cleaner.deduplicate(cleaned.name, cleaned.shop, cleaned.platform):
                logger.debug("Duplicate skipped: {} @ {} @ {}", cleaned.name, cleaned.shop, cleaned.platform)
                continue

            results.append(cleaned)

        logger.info("Pipeline: {} / {} products passed", len(results), len(raw_products))
        return results

    # ── Utilities ─────────────────────────────────────────────

    def reset(self) -> None:
        """Clear deduplication history."""
        self._cleaner.reset()
