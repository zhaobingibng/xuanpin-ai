"""Product trend analyzer — multi-dimension trend scoring from history data."""

from __future__ import annotations

from loguru import logger

from app.models.product_history import ProductHistory
from app.services.analytics.trend import growth_rate, growth_to_score

# ── Scoring weights ────────────────────────────────────────────

_WEIGHT_SALES = 0.50
_WEIGHT_VIEWS = 0.30
_WEIGHT_PRICE = 0.20

# ── Level thresholds ──────────────────────────────────────────

_LEVEL_EXPLOSIVE = "爆发"   # > 90
_LEVEL_RISING = "上涨"      # 70–90
_LEVEL_STABLE = "稳定"      # 50–70
_LEVEL_DECLINING = "下降"   # < 50


class TrendAnalyzer:
    """分析商品历史数据的趋势，输出评分和等级。

    Usage::

        analyzer = TrendAnalyzer(history_list)
        result = analyzer.analyze()
        # {"trend_score": 72.5, "sales_growth": 45.0,
        #  "view_growth": 30.0, "price_change": -10.0, "level": "上涨"}
    """

    def __init__(self, history: list[ProductHistory]) -> None:
        self._history = sorted(history, key=lambda h: h.record_time)

    # ── Public API ────────────────────────────────────────────

    def calculate_sales_growth(self) -> float:
        """计算销量增长率（最早 → 最新）。

        Returns:
            百分比增长率，0.0 表示无变化。
        """
        if len(self._history) < 2:
            return 0.0
        return growth_rate(self._history[0].sales_24h, self._history[-1].sales_24h)

    def calculate_view_growth(self) -> float:
        """计算浏览增长率（最早 → 最新）。

        Returns:
            百分比增长率，0.0 表示无变化。
        """
        if len(self._history) < 2:
            return 0.0
        return growth_rate(self._history[0].viewers, self._history[-1].viewers)

    def calculate_price_change(self) -> float:
        """计算价格变化比例（最早 → 最新）。

        Returns:
            百分比变化（负数 = 降价，正数 = 涨价）。
        """
        if len(self._history) < 2:
            return 0.0
        return growth_rate(self._history[0].price, self._history[-1].price)

    def calculate_trend_score(self) -> dict:
        """计算趋势评分，返回完整分析结果。

        评分规则：
            销量增长 50% + 浏览增长 30% + 价格优势 20%

        等级：
            >90 爆发 | 70-90 上涨 | 50-70 稳定 | <50 下降

        Returns:
            Dict with keys: trend_score, sales_growth, view_growth,
            price_change, level.
        """
        sales_g = self.calculate_sales_growth()
        view_g = self.calculate_view_growth()
        price_c = self.calculate_price_change()

        # 各维度得分（价格下降 = 优势 → 取反）
        sales_score = growth_to_score(sales_g)
        view_score = growth_to_score(view_g)
        price_score = growth_to_score(-price_c)

        trend_score = round(
            sales_score * _WEIGHT_SALES
            + view_score * _WEIGHT_VIEWS
            + price_score * _WEIGHT_PRICE,
            2,
        )

        level = self._determine_level(trend_score)

        result = {
            "trend_score": trend_score,
            "sales_growth": sales_g,
            "view_growth": view_g,
            "price_change": price_c,
            "level": level,
        }

        logger.debug(
            "TrendAnalyzer: score={}, level={}, sales_g={}%, view_g={}%, price_c={}%",
            trend_score, level, sales_g, view_g, price_c,
        )
        return result

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _determine_level(score: float) -> str:
        if score > 90:
            return _LEVEL_EXPLOSIVE
        if score >= 70:
            return _LEVEL_RISING
        if score >= 50:
            return _LEVEL_STABLE
        return _LEVEL_DECLINING
