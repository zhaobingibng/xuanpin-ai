"""Competition analyzer — assess market opportunity for each product."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class CompetitionAnalyzer:
    """市场竞争分析引擎。

    从三个维度评估商品的竞争环境：
      1. 价格优势（30分）：与同分类平均价格比较
      2. 销量优势（30分）：与同分类平均销量比较
      3. 市场竞争度（40分）：同分类商品数量

    competition_score: 0-100，越高竞争越有利（进入机会越好）
    market_level: LOW（竞争低，机会好）/ MEDIUM / HIGH（竞争激烈）

    Usage::

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(product_id=1)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Public API ────────────────────────────────────────────

    async def analyze(self, product_id: int) -> dict[str, Any]:
        """分析指定商品的市场竞争状况。

        Args:
            product_id: 商品 ID。

        Returns:
            {
                "product_id": int,
                "competition_score": int,  # 0-100
                "market_level": str,       # LOW / MEDIUM / HIGH
                "signals": list[str],
            }
        """
        product = await self._session.get(Product, product_id)
        if product is None:
            return {
                "product_id": product_id,
                "competition_score": 0,
                "market_level": "HIGH",
                "signals": ["商品不存在"],
            }

        # 获取同分类商品统计
        stats = await self._get_category_stats(product.category)

        price_score, price_signals = self._score_price(product, stats)
        sales_score, sales_signals = self._score_sales(product, stats)
        market_score, market_signals = self._score_market(stats)

        competition_score = price_score + sales_score + market_score
        competition_score = max(0, min(100, competition_score))
        market_level = self._determine_market_level(competition_score)

        signals = price_signals + sales_signals + market_signals

        logger.debug(
            "[CompetitionAnalyzer] product_id={}, score={}, level={}",
            product_id, competition_score, market_level,
        )

        return {
            "product_id": product_id,
            "competition_score": competition_score,
            "market_level": market_level,
            "signals": signals,
        }

    # ── Category statistics ───────────────────────────────────

    async def _get_category_stats(self, category: str | None) -> dict[str, Any]:
        """查询同分类商品的统计信息。

        Returns:
            {"avg_price": float, "avg_sales": float, "count": int}
        """
        if not category:
            # 无分类时与全部商品比较
            stmt = select(
                func.avg(Product.price),
                func.avg(Product.sales_24h),
                func.count(Product.id),
            )
        else:
            stmt = select(
                func.avg(Product.price),
                func.avg(Product.sales_24h),
                func.count(Product.id),
            ).where(Product.category == category)

        result = await self._session.execute(stmt)
        row = result.one()

        return {
            "avg_price": float(row[0] or 0),
            "avg_sales": float(row[1] or 0),
            "count": int(row[2] or 0),
        }

    # ── Price advantage (30 pts) ──────────────────────────────

    @staticmethod
    def _score_price(
        product: Product, stats: dict[str, Any]
    ) -> tuple[int, list[str]]:
        """价格优势评分：低于市场平均得分更高。"""
        avg_price = stats["avg_price"]
        signals: list[str] = []

        if avg_price <= 0:
            # 无数据时给中间分
            return 20, []

        ratio = product.price / avg_price

        if ratio <= 0.8:
            # 低于平均 20% 以上
            signals.append("价格低于市场平均")
            return 30, signals
        elif ratio < 1.0:
            # 低于平均但不足 20%
            signals.append("价格略低于市场")
            return 20, signals
        else:
            # 高于或等于平均
            return 10, []

    # ── Sales advantage (30 pts) ──────────────────────────────

    @staticmethod
    def _score_sales(
        product: Product, stats: dict[str, Any]
    ) -> tuple[int, list[str]]:
        """销量优势评分：超过平均得分更高。"""
        avg_sales = stats["avg_sales"]
        signals: list[str] = []

        if avg_sales <= 0:
            return 20, []

        ratio = product.sales_24h / avg_sales

        if ratio > 1.0:
            # 超过平均
            signals.append("销量超过市场平均")
            return 30, signals
        elif ratio >= 0.8:
            # 接近平均（80%-100%）
            signals.append("销量接近市场平均")
            return 20, signals
        else:
            # 低于平均
            return 10, []

    # ── Market competition (40 pts) ───────────────────────────

    @staticmethod
    def _score_market(stats: dict[str, Any]) -> tuple[int, list[str]]:
        """市场竞争度评分：同类商品越少竞争越低，机会越好。"""
        count = stats["count"]
        signals: list[str] = []

        if count <= 5:
            signals.append("竞争商品较少")
            return 40, signals
        elif count <= 15:
            signals.append("市场竞争适中")
            return 25, signals
        else:
            signals.append("市场竞争激烈")
            return 10, signals

    # ── Market level ──────────────────────────────────────────

    @staticmethod
    def _determine_market_level(score: int) -> str:
        """根据 competition_score 判断市场等级。

        score >= 80 → LOW（竞争低，机会好）
        50-79       → MEDIUM
        < 50        → HIGH（竞争激烈）
        """
        if score >= 80:
            return "LOW"
        elif score >= 50:
            return "MEDIUM"
        else:
            return "HIGH"
