"""Product comprehensive scoring engine — 0-100 score for product discovery."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.analytics.analyzer import TrendAnalyzer


# ── Level labels ──────────────────────────────────────────────

_LEVEL_HOT = "爆款"
_LEVEL_POTENTIAL = "潜力"
_LEVEL_NORMAL = "一般"
_LEVEL_LOW = "低潜"

# ── Default profit score ─────────────────────────────────────

_DEFAULT_PROFIT_SCORE = 10


class ProductScorer:
    """商品综合评分引擎。

    5 个维度，总分 100：
        1. 销量表现 (30)
        2. 增长趋势 (25) — 使用 TrendAnalyzer
        3. 浏览热度 (15)
        4. 价格竞争力 (15)
        5. 利润潜力 (15) — 暂默认 10

    支持动态权重：传入 weights 字典时按比例缩放各维度。

    Usage::

        scorer = ProductScorer()
        result = scorer.calculate_score(product, history)
        # {"score": 78, "level": "潜力", "reasons": [...]}

        # 使用动态权重
        result = scorer.calculate_score(product, history, weights={
            "sales_weight": 0.35, "trend_weight": 0.25,
            "viewer_weight": 0.15, "price_weight": 0.15,
            "competition_weight": 0.10,
        })
    """

    # ── Dimension max scores (for weight scaling) ─────────────

    _DIMENSION_MAX: dict[str, int] = {
        "sales_weight": 30,
        "trend_weight": 25,
        "viewer_weight": 15,
        "price_weight": 15,
        "competition_weight": 15,
    }

    # ── Public API ────────────────────────────────────────────

    def calculate_score(
        self,
        product: Product,
        history: list[ProductHistory] | None = None,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """计算商品综合评分。

        Args:
            product: 商品 ORM 实例。
            history: 该商品的历史快照列表（可选）。
            weights: 动态权重字典（可选），None 时使用默认固定权重。

        Returns:
            {"score": int, "level": str, "reasons": list[str]}
        """
        reasons: list[str] = []

        sales_score = self._score_sales(product.sales_24h, reasons)
        trend_score = self._score_trend(history, product.sales_24h, reasons)
        viewers_score = self._score_viewers(product.viewers, reasons)
        price_score = self._score_price(product.price, reasons)

        if weights is not None:
            # ── 动态权重模式 ──────────────────────────────────
            raw_scores = {
                "sales_weight": sales_score,
                "trend_weight": trend_score,
                "viewer_weight": viewers_score,
                "price_weight": price_score,
                "competition_weight": _DEFAULT_PROFIT_SCORE,
            }

            total = 0.0
            for dim, raw in raw_scores.items():
                w = weights.get(dim, 0.0)
                max_val = self._DIMENSION_MAX.get(dim, 15)
                # Scale: (raw / max_val) * weight * 100
                total += (raw / max_val) * w * 100

            total = min(100, max(0, int(round(total))))
        else:
            # ── 固定权重模式（向后兼容） ──────────────────────
            profit_score = _DEFAULT_PROFIT_SCORE
            total = sales_score + trend_score + viewers_score + price_score + profit_score

        level = self._determine_level(total)

        result = {
            "score": total,
            "level": level,
            "reasons": reasons,
        }

        logger.debug(
            "ProductScorer: {} → score={}, level={}, reasons={}",
            product.name, total, level, reasons,
        )
        return result

    # ── Dimension scores ──────────────────────────────────────

    @staticmethod
    def _score_sales(sales_24h: int, reasons: list[str]) -> int:
        """销量表现评分 (max 30)。"""
        if sales_24h >= 10_000:
            score = 30
        elif sales_24h >= 5_000:
            score = 25
        elif sales_24h >= 1_000:
            score = 20
        elif sales_24h >= 100:
            score = 10
        else:
            score = 5

        reasons.append(f"24小时销量{sales_24h}")
        return score

    @staticmethod
    def _score_trend(
        history: list[ProductHistory] | None,
        sales_24h: int,
        reasons: list[str],
    ) -> int:
        """增长趋势评分 (max 25)。

        使用 TrendAnalyzer 计算增长率，再按区间映射到分数。
        """
        if not history or len(history) < 2:
            reasons.append("暂无趋势数据")
            return 5

        analyzer = TrendAnalyzer(history)
        sales_growth = analyzer.calculate_sales_growth()

        if sales_growth > 100:
            score = 25
        elif sales_growth >= 50:
            score = 20
        elif sales_growth >= 10:
            score = 15
        elif sales_growth >= 0:
            score = 10
        else:
            score = 5

        reasons.append(f"增长率{sales_growth:.0f}%")
        return score

    @staticmethod
    def _score_viewers(viewers: int, reasons: list[str]) -> int:
        """浏览热度评分 (max 15)。"""
        if viewers >= 50_000:
            score = 15
        elif viewers >= 10_000:
            score = 10
        elif viewers >= 1_000:
            score = 7
        else:
            score = 3

        reasons.append(f"浏览热度{viewers}")
        return score

    @staticmethod
    def _score_price(price: float, reasons: list[str]) -> int:
        """价格竞争力评分 (max 15)。"""
        if 20 <= price <= 200:
            score = 15
        elif 10 <= price < 20 or 200 < price <= 500:
            score = 10
        else:
            score = 5

        reasons.append(f"价格{price}")
        return score

    # ── Level ─────────────────────────────────────────────────

    @staticmethod
    def _determine_level(score: int) -> str:
        if score >= 90:
            return _LEVEL_HOT
        if score >= 70:
            return _LEVEL_POTENTIAL
        if score >= 50:
            return _LEVEL_NORMAL
        return _LEVEL_LOW
