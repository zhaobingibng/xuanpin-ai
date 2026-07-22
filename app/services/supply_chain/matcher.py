"""SupplyChainMatcher — [DEPRECATED] match retail products with 1688 suppliers.

请使用 SupplierMatchingService.match_products_with_matcher() 替代。

Combines title similarity (SequenceMatcher) with optional image similarity
(dHash) for robust product matching.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch
from app.services.supply_chain.provider import SupplyChainProvider, SupplierProduct


class SupplyChainMatcher:
    """[DEPRECATED] 基于标题 + 图片相似度匹配 1688 供应链。

    请使用 SupplierMatchingService.match_products_with_matcher() 替代。

    使用 SupplyChainProvider 获取供应商数据（真实爬虫 + Mock 降级）。
    使用 difflib.SequenceMatcher 计算标题相似度。
    可选使用 ImageSimilarityMatcher (dHash) 计算图片相似度。
    最终得分 = title_weight * title_sim + image_weight * image_sim。

    Usage::

        matcher = SupplyChainMatcher(session)
        result = await matcher.match_product(product)
    """

    # 最低匹配阈值，低于此值不认为匹配
    MIN_SCORE_THRESHOLD: float = 0.35

    # 权重配置
    TITLE_WEIGHT: float = 0.6  # 标题权重
    IMAGE_WEIGHT: float = 0.4  # 图片权重 (仅当图片可用时)

    def __init__(
        self,
        session: AsyncSession,
        provider: SupplyChainProvider | None = None,
        enable_image_match: bool = False,
    ) -> None:
        self._session = session
        self._provider = provider  # Lazy init on first use
        self._enable_image_match = enable_image_match
        self._image_matcher = None  # Lazy init

    def _get_image_matcher(self):
        """Lazy-init ImageSimilarityMatcher."""
        if self._image_matcher is None and self._enable_image_match:
            from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
            self._image_matcher = ImageSimilarityMatcher()
        return self._image_matcher

    async def _get_provider(self) -> SupplyChainProvider:
        """Lazy-init the supply chain provider."""
        if self._provider is None:
            self._provider = SupplyChainProvider()
        return self._provider

    async def match_product(
        self,
        product: Product,
        min_score: float | None = None,
    ) -> SupplyChainMatch | None:
        """为单个商品匹配 1688 供应链。

        Args:
            product: 待匹配的淘宝商品。
            min_score: 最低匹配阈值，None 使用默认阈值。

        Returns:
            匹配结果，无匹配时返回 None。
        """
        threshold = min_score if min_score is not None else self.MIN_SCORE_THRESHOLD

        # Get candidates from provider (real + mock fallback)
        provider = await self._get_provider()
        candidates = await provider.search(product.name, limit=20)

        image_matcher = self._get_image_matcher()
        best_match: SupplierProduct | None = None
        best_score: float = 0.0
        best_match_type: str = "title"

        for candidate in candidates:
            title_sim = self._title_similarity(product.name, candidate.title)

            # Try image similarity if enabled and URLs available
            if image_matcher is not None and title_sim > 0.2:
                # Get product image URL (from image field or None)
                product_img = getattr(product, "image", None) or ""
                supplier_img = getattr(candidate, "image_url", None) or ""

                if product_img and supplier_img:
                    img_sim = image_matcher.compare_urls(product_img, supplier_img)
                    if img_sim > 0.3:
                        # Combined score: weighted sum
                        combined = (
                            self.TITLE_WEIGHT * title_sim
                            + self.IMAGE_WEIGHT * img_sim
                        )
                        if combined > best_score:
                            best_score = combined
                            best_match = candidate
                            best_match_type = "title+image"
                        continue

            # Title-only fallback
            if title_sim > best_score:
                best_score = title_sim
                best_match = candidate
                best_match_type = "title"

        if best_match is None or best_score < threshold:
            logger.debug(
                "[SupplyChainMatcher] 无匹配: '{}' (最高分={:.2f}, 阈值={:.2f})",
                product.name[:30], best_score, threshold,
            )
            return None

        # 计算利润
        sell_price = product.price
        cost_price = best_match.price
        profit = self._calculate_profit(sell_price, cost_price)

        # 创建匹配记录
        match = SupplyChainMatch(
            product_id=product.id,
            source_product_id=None,
            source_product_external_id=best_match.product_id,
            match_score=round(best_score, 4),
            match_type=best_match_type,
            cost_price=cost_price,
            sell_price=sell_price,
            profit_margin=round(profit["margin"], 2),
            profit_amount=round(profit["amount"], 2),
            platform_fee_rate=profit["fee_rate"],
            shipping_cost=profit["shipping"],
            status="MATCHED",
        )
        self._session.add(match)
        await self._session.commit()
        await self._session.refresh(match)

        logger.info(
            "[SupplyChainMatcher] 匹配成功: '{}' → '{}' (score={:.2f}, type={}, margin={:.1f}%)",
            product.name[:30], best_match.title[:30], best_score, best_match_type, profit["margin"],
        )
        return match

    async def match_batch(
        self,
        products: list[Product],
        min_score: float | None = None,
    ) -> list[SupplyChainMatch]:
        """批量匹配商品。

        Args:
            products: 待匹配商品列表。
            min_score: 最低匹配分数。

        Returns:
            成功匹配的结果列表。
        """
        matches: list[SupplyChainMatch] = []
        for product in products:
            try:
                match = await self.match_product(product, min_score=min_score)
                if match is not None:
                    matches.append(match)
            except Exception as e:
                logger.warning("[SupplyChainMatcher] 匹配失败: product_id={} → {}", product.id, e)

        logger.info(
            "[SupplyChainMatcher] 批量匹配完成: {}/{} 个商品成功匹配",
            len(matches), len(products),
        )
        return matches

    @staticmethod
    def _title_similarity(title_a: str, title_b: str) -> float:
        """计算两个标题的相似度 (0-1)。"""
        if not title_a or not title_b:
            return 0.0
        return SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()

    @staticmethod
    def _calculate_profit(
        sell_price: float,
        cost_price: float,
        fee_rate: float = 0.05,
        shipping: float = 5.0,
    ) -> dict[str, float]:
        """计算利润空间。

        Args:
            sell_price: 售价。
            cost_price: 成本价。
            fee_rate: 平台佣金率 (默认 5%)。
            shipping: 运费 (默认 5 元)。

        Returns:
            {"amount": 利润额, "margin": 利润率%, "fee_rate": 佣金率, "shipping": 运费}
        """
        if sell_price <= 0:
            return {"amount": 0.0, "margin": 0.0, "fee_rate": fee_rate, "shipping": shipping}

        fee = sell_price * fee_rate
        amount = sell_price - cost_price - fee - shipping
        margin = (amount / sell_price) * 100 if sell_price > 0 else 0.0

        return {
            "amount": amount,
            "margin": margin,
            "fee_rate": fee_rate,
            "shipping": shipping,
        }
