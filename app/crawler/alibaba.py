"""Alibaba (1688) supplier search interface — 简化版.

提供统一的供应商搜索接口，支持：
1. 真实1688爬虫（需要登录）
2. Mock模式（用于测试和演示）

Usage::

    from app.crawler.alibaba import AlibabaSearchClient

    client = AlibabaSearchClient()
    results = await client.search_products("芋泥蛋皮吐司卷")
    # [{"title": "...", "url": "...", "price": 18.0}, ...]
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class AlibabaSearchClient:
    """1688供应商搜索客户端。

    提供简化的搜索接口，内部可调用 Alibaba1688Crawler。
    """

    def __init__(self, crawler: Any = None, use_mock: bool = False):
        """初始化搜索客户端。

        Args:
            crawler: Alibaba1688Crawler 实例（可选）。
            use_mock: 是否使用 Mock 数据（测试用）。
        """
        self._crawler = crawler
        self._use_mock = use_mock

    async def search_products(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """搜索1688供应商商品。

        Args:
            keyword: 搜索关键词。
            limit: 最大返回数量。

        Returns:
            商品列表，格式:
            [{"title": "...", "url": "...", "price": 18.0}, ...]
        """
        if self._use_mock:
            return self._mock_search(keyword, limit)

        if self._crawler:
            return await self._real_search(keyword, limit)

        # 无爬虫且非Mock模式，返回空
        logger.warning("[AlibabaSearch] No crawler configured, returning empty results")
        return []

    async def _real_search(
        self,
        keyword: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """真实搜索（调用爬虫）。"""
        try:
            supplier_products = await self._crawler.search_suppliers(
                keyword=keyword,
                limit=limit,
            )

            return [
                {
                    "title": sp.title,
                    "url": sp.url,
                    "image_url": sp.image_url,
                    "price": sp.price,
                    "supplier_name": sp.supplier_name,
                }
                for sp in supplier_products
            ]
        except Exception as e:
            logger.error("[AlibabaSearch] Real search failed: {}", e)
            return []

    def _mock_search(
        self,
        keyword: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Mock搜索（测试用）。

        返回模拟的1688商品数据。
        """
        logger.info("[AlibabaSearch] Using mock data for keyword: {}", keyword)

        # 模拟数据：根据关键词生成相关结果
        mock_results = [
            {
                "title": f"{keyword} 厂家直销 批发",
                "url": f"https://detail.1688.com/offer/mock_{keyword[:10]}.html",
                "image_url": f"https://cbu01.alicdn.com/img/mock_{keyword[:10]}.jpg",
                "price": 15.0,
                "supplier_name": "某某食品厂",
            },
            {
                "title": f"{keyword} 工厂货源 现货",
                "url": f"https://detail.1688.com/offer/mock_{keyword[:10]}_2.html",
                "image_url": f"https://cbu01.alicdn.com/img/mock_{keyword[:10]}_2.jpg",
                "price": 18.0,
                "supplier_name": "某某零食批发",
            },
            {
                "title": f"优质{keyword} 一件代发",
                "url": f"https://detail.1688.com/offer/mock_{keyword[:10]}_3.html",
                "image_url": f"https://cbu01.alicdn.com/img/mock_{keyword[:10]}_3.jpg",
                "price": 20.0,
                "supplier_name": "某某贸易公司",
            },
        ]

        return mock_results[:limit]
