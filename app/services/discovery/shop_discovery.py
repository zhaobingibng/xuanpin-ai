"""ShopDiscoveryService — auto-discover high-value shops from crawl results.

Analyzes product crawl data to identify and score shops, then registers
high-value shops to ShopRegistry for ongoing monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.models.schemas import RawProduct
from app.services.shop_service import ShopService


@dataclass
class ShopStats:
    """Aggregated statistics for a discovered shop."""

    shop_name: str
    platform: str
    product_count: int = 0
    total_sales: int = 0
    avg_price: float = 0.0
    min_price: float = 0.0
    max_price: float = 0.0
    categories: set[str] = field(default_factory=set)
    total_favorites: int = 0
    sample_url: str | None = None

    @property
    def category_count(self) -> int:
        return len(self.categories)


@dataclass
class ShopScore:
    """Scoring result for a shop."""

    shop_name: str
    platform: str
    score: float  # 0-100
    product_count_score: float
    sales_score: float
    price_score: float
    diversity_score: float
    stats: ShopStats


class ShopDiscoveryService:
    """Auto-discover and score shops from product crawl data.

    Usage::

        svc = ShopDiscoveryService(session)
        # After crawling, analyze the results
        results = await svc.discover_from_products(raw_products)
        # results contains scored shops
        # High-value shops are automatically registered
    """

    # Scoring weights
    WEIGHT_PRODUCT_COUNT = 0.30
    WEIGHT_SALES = 0.35
    WEIGHT_PRICE = 0.15
    WEIGHT_DIVERSITY = 0.20

    # Thresholds
    MIN_SCORE_TO_REGISTER = 40.0  # Minimum score to auto-register
    MIN_PRODUCTS_TO_CONSIDER = 2  # At least 2 products in results

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._shop_service = ShopService(session)

    async def discover_from_products(
        self,
        products: list[RawProduct],
        *,
        auto_register: bool = True,
        min_score: float = MIN_SCORE_TO_REGISTER,
    ) -> list[ShopScore]:
        """Discover and score shops from a list of raw products.

        Args:
            products: RawProduct list from crawl results.
            auto_register: Whether to auto-register high-scoring shops.
            min_score: Minimum score threshold for auto-registration.

        Returns:
            List of ShopScore sorted by score descending.
        """
        if not products:
            return []

        # Step 1: Aggregate by shop
        shop_stats = self._aggregate_by_shop(products)
        logger.info("[ShopDiscovery] Aggregated {} shops from {} products", len(shop_stats), len(products))

        # Step 2: Filter shops with minimum products
        qualified = {
            name: stats
            for name, stats in shop_stats.items()
            if stats.product_count >= self.MIN_PRODUCTS_TO_CONSIDER
        }
        logger.info("[ShopDiscovery] {} shops meet minimum product threshold", len(qualified))

        # Step 3: Score each shop
        scored = []
        for name, stats in qualified.items():
            score = self._score_shop(stats)
            scored.append(score)

        # Sort by score descending
        scored.sort(key=lambda s: s.score, reverse=True)

        # Step 4: Auto-register high-value shops
        if auto_register:
            registered_count = 0
            for shop_score in scored:
                if shop_score.score < min_score:
                    continue
                # Check if already registered
                existing = await self._shop_service.find_by_shop_id(
                    shop_score.platform, shop_score.shop_name
                )
                if existing:
                    continue

                # Generate a shop_id from name (hash-based)
                shop_id = self._generate_shop_id(shop_score.shop_name, shop_score.platform)

                try:
                    await self._shop_service.register_or_update(
                        platform=shop_score.platform,
                        shop_id=shop_id,
                        shop_name=shop_score.shop_name,
                        shop_url=shop_score.stats.sample_url,
                        category=self._primary_category(shop_score.stats),
                        fans=0,  # Unknown from crawl data
                        priority=self._score_to_priority(shop_score.score),
                        enabled=True,
                        monitor_strategy="daily",
                    )
                    registered_count += 1
                except Exception as e:
                    logger.warning(
                        "[ShopDiscovery] Failed to register shop '{}': {}",
                        shop_score.shop_name, e,
                    )

            logger.info("[ShopDiscovery] Auto-registered {} new shops", registered_count)

        return scored

    def _aggregate_by_shop(self, products: list[RawProduct]) -> dict[str, ShopStats]:
        """Aggregate product data by shop name."""
        stats_map: dict[str, ShopStats] = {}

        for prod in products:
            shop_name = prod.shop
            if not shop_name or shop_name == "未知店铺":
                continue

            if shop_name not in stats_map:
                stats_map[shop_name] = ShopStats(
                    shop_name=shop_name,
                    platform=prod.platform,
                )

            stats = stats_map[shop_name]
            stats.product_count += 1
            stats.total_sales += prod.sales_24h
            stats.total_favorites += prod.favorites

            # Price tracking
            if stats.min_price == 0 or prod.price < stats.min_price:
                stats.min_price = prod.price
            if prod.price > stats.max_price:
                stats.max_price = prod.price

            # Category
            if prod.category:
                stats.categories.add(prod.category)

            # Sample URL — prefer direct shop_url from crawler (Phase 16)
            if stats.sample_url is None:
                if prod.shop_url:
                    stats.sample_url = prod.shop_url
                elif prod.url:
                    stats.sample_url = self._extract_shop_url(prod.url)

        # Calculate average price
        for stats in stats_map.values():
            if stats.product_count > 0:
                prices = [stats.min_price, stats.max_price]
                stats.avg_price = sum(prices) / len(prices)

        return stats_map

    def _score_shop(self, stats: ShopStats) -> ShopScore:
        """Calculate composite score for a shop (0-100)."""
        # Product count score (log scale, max at 20+ products)
        import math
        product_score = min(100, math.log1p(stats.product_count) / math.log1p(20) * 100)

        # Sales score (log scale, max at 10000+ total sales)
        sales_score = min(100, math.log1p(stats.total_sales) / math.log1p(10000) * 100)

        # Price score (prefer mid-range products, 50-500 is ideal)
        avg = stats.avg_price
        if avg <= 0:
            price_score = 0
        elif 50 <= avg <= 500:
            price_score = 100
        elif avg < 50:
            price_score = max(0, avg / 50 * 100)
        else:
            price_score = max(0, 100 - (avg - 500) / 10)

        # Diversity score (more categories = better)
        diversity_score = min(100, stats.category_count * 25)

        # Weighted composite
        total = (
            product_score * self.WEIGHT_PRODUCT_COUNT
            + sales_score * self.WEIGHT_SALES
            + price_score * self.WEIGHT_PRICE
            + diversity_score * self.WEIGHT_DIVERSITY
        )

        return ShopScore(
            shop_name=stats.shop_name,
            platform=stats.platform,
            score=round(total, 2),
            product_count_score=round(product_score, 2),
            sales_score=round(sales_score, 2),
            price_score=round(price_score, 2),
            diversity_score=round(diversity_score, 2),
            stats=stats,
        )

    @staticmethod
    def _generate_shop_id(shop_name: str, platform: str) -> str:
        """Generate a deterministic shop_id from name + platform."""
        import hashlib
        raw = f"{platform}:{shop_name}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_shop_url(product_url: str) -> str | None:
        """Try to extract shop homepage URL from a product URL."""
        if not product_url:
            return None
        # For taobao/tmall product URLs, extract shop domain
        try:
            from urllib.parse import urlparse
            parsed = urlparse(product_url)
            # item.taobao.com -> shop*.taobao.com
            if "taobao.com" in parsed.netloc:
                return f"https://{parsed.netloc}"
            if "tmall.com" in parsed.netloc:
                return f"https://{parsed.netloc}"
        except Exception:
            pass
        return None

    @staticmethod
    def _primary_category(stats: ShopStats) -> str | None:
        """Get the primary (first) category from stats."""
        if stats.categories:
            return next(iter(stats.categories))
        return None

    @staticmethod
    def _score_to_priority(score: float) -> int:
        """Convert score to priority level (1-3)."""
        if score >= 70:
            return 3  # High
        elif score >= 50:
            return 2  # Medium
        return 1  # Low
