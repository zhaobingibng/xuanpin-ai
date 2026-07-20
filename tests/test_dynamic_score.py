"""Tests for ProductScorer dynamic weights — backward compat + weight scaling."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.scoring.product_scorer import ProductScorer


def _product(
    sales_24h: int = 5000,
    viewers: int = 10000,
    price: float = 99.0,
    name: str = "测试商品",
) -> Product:
    return Product(
        id=1, name=name, platform="xiaohongshu", shop="测试店铺",
        price=price, sales_24h=sales_24h, viewers=viewers,
    )


def _history_list(
    sales: list[int],
    viewers: list[int] | None = None,
    price: float = 99.0,
) -> list[ProductHistory]:
    if viewers is None:
        viewers = [0] * len(sales)
    now = datetime.utcnow()
    records = []
    for i, (s, v) in enumerate(zip(sales, viewers)):
        records.append(ProductHistory(
            product_id=1,
            price=price,
            sales_24h=s,
            viewers=v,
            record_time=now - timedelta(minutes=(len(sales) - i) * 60),
        ))
    return records


# ── Backward compatibility ───────────────────────────────


class TestBackwardCompat:
    """不传 weights 时保持原有行为。"""

    def test_default_scoring_unchanged(self):
        """无 weights 参数时使用原有固定权重。"""
        scorer = ProductScorer()
        p = _product(sales_24h=10000, viewers=50000, price=99.0)
        result = scorer.calculate_score(p)
        # sales(30) + trend(5) + viewers(15) + price(15) + profit(10) = 75
        assert result["score"] == 75

    def test_default_score_range(self):
        """默认评分应在合理范围内。"""
        scorer = ProductScorer()
        p = _product()
        result = scorer.calculate_score(p)
        assert 0 <= result["score"] <= 100
        assert result["level"] in ("爆款", "潜力", "一般", "低潜")

    def test_default_reasons_present(self):
        """默认模式应有 reasons 列表。"""
        scorer = ProductScorer()
        p = _product()
        result = scorer.calculate_score(p)
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) >= 4


# ── Dynamic weights ──────────────────────────────────────


class TestDynamicWeights:
    """传入 weights 时使用动态权重。"""

    def test_weights_affect_score(self):
        """不同的权重应产生不同的评分。"""
        scorer = ProductScorer()
        # 高销量(30/30) 低浏览(3/15) — 销量维度远强于浏览维度
        p = _product(sales_24h=10000, viewers=100, price=99.0)

        # 高销量权重 → 高分
        weights_high_sales = {
            "sales_weight": 0.60,
            "trend_weight": 0.10,
            "viewer_weight": 0.10,
            "price_weight": 0.10,
            "competition_weight": 0.10,
        }
        # 高浏览权重 → 低分（因为浏览原始分低）
        weights_high_viewers = {
            "sales_weight": 0.10,
            "trend_weight": 0.10,
            "viewer_weight": 0.60,
            "price_weight": 0.10,
            "competition_weight": 0.10,
        }

        r1 = scorer.calculate_score(p, weights=weights_high_sales)
        r2 = scorer.calculate_score(p, weights=weights_high_viewers)

        # 高销量权重应得更高分（因为销量原始分 30/30，浏览只有 3/15）
        assert r1["score"] > r2["score"]

    def test_score_bounded_0_100(self):
        """动态权重模式下评分应在 0-100 范围内。"""
        scorer = ProductScorer()
        p = _product(sales_24h=10000, viewers=50000, price=99.0)
        weights = {
            "sales_weight": 0.50,
            "trend_weight": 0.20,
            "viewer_weight": 0.15,
            "price_weight": 0.10,
            "competition_weight": 0.05,
        }
        result = scorer.calculate_score(p, weights=weights)
        assert 0 <= result["score"] <= 100

    def test_default_weights_similar_to_fixed(self):
        """使用默认权重时应与固定权重评分接近。"""
        scorer = ProductScorer()
        p = _product(sales_24h=5000, viewers=10000, price=99.0)

        default_result = scorer.calculate_score(p)
        weighted_result = scorer.calculate_score(p, weights={
            "sales_weight": 0.30,
            "trend_weight": 0.25,
            "viewer_weight": 0.15,
            "price_weight": 0.15,
            "competition_weight": 0.15,
        })

        # 两者应在合理范围内接近（不完全相同因为计算方式不同）
        assert abs(default_result["score"] - weighted_result["score"]) < 30

    def test_zero_weight_dimension_ignored(self):
        """权重为 0 的维度不影响评分。"""
        scorer = ProductScorer()
        p = _product(sales_24h=10000, viewers=50000, price=99.0)

        # sales 权重为 0
        weights = {
            "sales_weight": 0.0,
            "trend_weight": 0.25,
            "viewer_weight": 0.25,
            "price_weight": 0.25,
            "competition_weight": 0.25,
        }
        r1 = scorer.calculate_score(p, weights=weights)

        # sales 权重仍然为 0，但商品销量不同
        p2 = _product(sales_24h=100, viewers=50000, price=99.0)
        r2 = scorer.calculate_score(p2, weights=weights)

        # sales 权重为 0，不同销量应产生相同评分
        assert r1["score"] == r2["score"]

    def test_high_competition_weight(self):
        """高竞争权重时评分有效。"""
        scorer = ProductScorer()
        p = _product(sales_24h=5000, viewers=10000, price=99.0)
        weights = {
            "sales_weight": 0.10,
            "trend_weight": 0.10,
            "viewer_weight": 0.10,
            "price_weight": 0.10,
            "competition_weight": 0.60,
        }
        result = scorer.calculate_score(p, weights=weights)
        assert 0 <= result["score"] <= 100
        assert result["level"] in ("爆款", "潜力", "一般", "低潜")

    def test_level_determination_with_weights(self):
        """动态权重下的 level 判断仍然正确。"""
        scorer = ProductScorer()

        # 高销量高浏览 → 应该得分较高
        p_high = _product(sales_24h=15000, viewers=60000, price=99.0)
        weights = {
            "sales_weight": 0.30,
            "trend_weight": 0.25,
            "viewer_weight": 0.20,
            "price_weight": 0.15,
            "competition_weight": 0.10,
        }
        result = scorer.calculate_score(p_high, weights=weights)
        # 高销量(30/30) + 高浏览(15/15) + 好价格(15/15) = high score
        assert result["score"] >= 60

    def test_with_history_and_weights(self):
        """有历史数据 + 动态权重时趋势分生效。"""
        scorer = ProductScorer()
        p = _product(sales_24h=5000, viewers=10000, price=99.0)
        history = _history_list(sales=[1000, 2000, 3000, 5000], viewers=[500, 1000, 2000, 10000])
        weights = {
            "sales_weight": 0.30,
            "trend_weight": 0.25,
            "viewer_weight": 0.15,
            "price_weight": 0.15,
            "competition_weight": 0.15,
        }
        result = scorer.calculate_score(p, history=history, weights=weights)
        assert 0 <= result["score"] <= 100
        # 有趋势数据时不应显示"暂无趋势数据"
        assert not any("暂无趋势数据" in r for r in result["reasons"])
