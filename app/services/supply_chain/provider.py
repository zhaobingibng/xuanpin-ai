"""SupplyChainProvider — unified data source for 1688 supplier products.

Abstracts the data source: tries real Alibaba1688Crawler first,
falls back to mock data if crawler is unavailable or returns empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger


@dataclass
class SupplierProduct:
    """Unified supplier product — used across the supply chain pipeline."""

    product_id: str
    title: str
    price: float
    min_order: int = 1
    supplier_name: str = ""
    supplier_location: str = ""
    monthly_sales: int = 0
    image_url: str | None = None
    url: str | None = None


class SupplyChainProvider:
    """Unified supplier data source with automatic fallback.

    Strategy:
    1. Try real Alibaba1688Crawler.search_suppliers()
    2. If it fails or returns empty → fall back to mock data
    3. Cache results for a configurable TTL to avoid excessive crawling

    Usage::

        provider = SupplyChainProvider()
        products = await provider.search("蓝牙耳机")
    """

    def __init__(
        self,
        use_real_crawler: bool = False,
        use_mock_fallback: bool = True,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._use_real_crawler = use_real_crawler
        self._use_mock_fallback = use_mock_fallback
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[list[SupplierProduct], datetime]] = {}
        self._crawler = None  # Lazy init

    async def _get_crawler(self):
        """Lazy-init the 1688 crawler."""
        if self._crawler is None:
            from app.crawler.alibaba_1688 import Alibaba1688Crawler
            self._crawler = Alibaba1688Crawler()
        return self._crawler

    async def search(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[SupplierProduct]:
        """Search for supplier products by keyword.

        Args:
            keyword: Product keyword to search.
            limit: Max results to return.

        Returns:
            List of SupplierProduct (from real or mock source).
        """
        # Check cache
        if keyword in self._cache:
            cached_results, cached_time = self._cache[keyword]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                logger.debug("[SupplyChainProvider] Cache hit for '{}'", keyword)
                return cached_results[:limit]

        # Try real crawler (only if explicitly enabled)
        results: list[SupplierProduct] = []
        if self._use_real_crawler:
            results = await self._search_real(keyword, limit)

        # Fallback to mock if empty
        if not results and self._use_mock_fallback:
            logger.debug("[SupplyChainProvider] Using mock data for '{}'", keyword)
            results = self._search_mock(keyword, limit)

        # Cache results
        if results:
            self._cache[keyword] = (results, datetime.now())

        return results[:limit]

    async def _search_real(self, keyword: str, limit: int) -> list[SupplierProduct]:
        """Search using real 1688 crawler."""
        try:
            crawler = await self._get_crawler()
            raw_results = await crawler.search_suppliers(keyword, limit=limit)
            return [
                SupplierProduct(
                    product_id=r.product_id,
                    title=r.title,
                    price=r.price,
                    min_order=r.min_order,
                    supplier_name=r.supplier_name,
                    supplier_location=r.supplier_location,
                    monthly_sales=r.monthly_sales,
                    image_url=r.image_url,
                    url=r.url,
                )
                for r in raw_results
            ]
        except Exception as e:
            logger.warning("[SupplyChainProvider] Real 1688 search failed: {}", e)
            return []

    @staticmethod
    def _search_mock(keyword: str, limit: int) -> list[SupplierProduct]:
        """Search using mock data as fallback.

        First tries keyword search; if empty, returns full catalog
        to maintain backward compatibility with the old matcher behavior.
        """
        from app.services.supply_chain.mock_data import search_1688_by_keyword, get_1688_catalog

        mock_results = search_1688_by_keyword(keyword, limit=limit)
        if not mock_results:
            # Fallback: return full catalog for title similarity matching
            mock_results = get_1688_catalog()[:limit]
        return [
            SupplierProduct(
                product_id=m.product_id,
                title=m.title,
                price=m.price,
                min_order=m.min_order,
                supplier_name=m.supplier_name,
                supplier_location=m.supplier_location,
                monthly_sales=m.monthly_sales,
                image_url=m.image_url,
                url=m.url,
            )
            for m in mock_results
        ]

    async def close(self) -> None:
        """Close the underlying crawler."""
        if self._crawler is not None:
            await self._crawler.close()
            self._crawler = None

    def clear_cache(self) -> None:
        """Clear the search cache."""
        self._cache.clear()
