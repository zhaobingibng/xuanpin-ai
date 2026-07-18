"""Crawler manager — orchestrates multiple platform crawlers."""

from loguru import logger

from app.crawler.base import BaseCrawler
from app.crawler.models.schemas import RawProduct


class CrawlerManager:
    """Manages registration and execution of platform crawlers.

    Usage::

        manager = CrawlerManager()
        manager.register(XiaohongshuCrawler())
        manager.register(DouyinCrawler())

        products = await manager.crawl("xiaohongshu", keyword="防晒霜")
        all_products = await manager.crawl_all(keyword="防晒霜")
    """

    def __init__(self) -> None:
        self._crawlers: dict[str, BaseCrawler] = {}

    # ── Registration ──────────────────────────────────────────

    def register(self, crawler: BaseCrawler) -> None:
        """Register a crawler by its PLATFORM name."""
        self._crawlers[crawler.PLATFORM] = crawler
        logger.info("Registered crawler: {}", crawler.PLATFORM)

    # ── Execution ─────────────────────────────────────────────

    async def crawl(
        self,
        platform: str,
        keyword: str,
        max_pages: int = 3,
    ) -> list[RawProduct]:
        """Run a single platform crawler by name."""
        crawler = self._crawlers.get(platform)
        if crawler is None:
            logger.error("No crawler registered for platform: {}", platform)
            return []
        return await crawler.crawl(keyword=keyword, max_pages=max_pages)

    async def crawl_all(
        self,
        keyword: str,
        max_pages: int = 3,
    ) -> dict[str, list[RawProduct]]:
        """Run all registered crawlers. Return per-platform results."""
        results: dict[str, list[RawProduct]] = {}
        for platform, crawler in self._crawlers.items():
            try:
                results[platform] = await crawler.crawl(
                    keyword=keyword, max_pages=max_pages
                )
            except Exception as e:
                logger.error("Crawler [{}] failed: {}", platform, e)
                results[platform] = []
        return results

    # ── Persistence ───────────────────────────────────────────

    async def save_to_db(self, products: list[RawProduct], session) -> int:
        """Persist raw products via ProductService. Return count saved."""
        from app.services.product_service import ProductService

        service = ProductService(session)
        saved = 0
        for product in products:
            try:
                await service.create(**product.to_db_kwargs())
                saved += 1
            except Exception as e:
                logger.warning("Failed to save product '{}': {}", product.name, e)
        logger.info("Saved {}/{} products to database", saved, len(products))
        return saved

    # ── Cleanup ───────────────────────────────────────────────

    async def close_all(self) -> None:
        """Close all registered crawlers."""
        for crawler in self._crawlers.values():
            await crawler.close()
        logger.info("All crawlers closed")

    # ── Introspection ─────────────────────────────────────────

    @property
    def platforms(self) -> list[str]:
        """List registered platform names."""
        return list(self._crawlers.keys())

    def __len__(self) -> int:
        return len(self._crawlers)
