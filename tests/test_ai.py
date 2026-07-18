"""Tests for AI scoring module: rules, scorer, analyzer."""

import pytest

from app.ai.rules import calculate_score, score_price, score_sales, score_viewers
from app.ai.scorer import ProductScorer
from app.ai.analyzer import ProductAnalyzer
from app.services.cleaner.pipeline import CleanedProduct


# ── Helpers ───────────────────────────────────────────────────


def _make_product(**overrides) -> CleanedProduct:
    defaults = {
        "name": "测试商品",
        "platform": "xiaohongshu",
        "shop": "测试店铺",
        "price": 99.0,
        "viewers": 5000,
        "sales_24h": 500,
        "category": "数码",
        "image": None,
    }
    defaults.update(overrides)
    return CleanedProduct(**defaults)


# ── Rules: score_sales ────────────────────────────────────────


class TestScoreSales:
    """5 groups for sales scoring."""

    def test_top_tier(self):
        assert score_sales(10000) == 100.0
        assert score_sales(50000) == 100.0

    def test_high_tier(self):
        assert score_sales(5000) == 80.0
        assert score_sales(9999) == 80.0

    def test_mid_tier(self):
        assert score_sales(1000) == 60.0
        assert score_sales(4999) == 60.0

    def test_low_tier(self):
        assert score_sales(100) == 20.0
        assert score_sales(0) == 0.0

    def test_boundary(self):
        assert score_sales(99) == 0.0
        assert score_sales(100) == 20.0
        assert score_sales(500) == 40.0


# ── Rules: score_viewers ──────────────────────────────────────


class TestScoreViewers:
    """5 groups for viewers scoring."""

    def test_top_tier(self):
        assert score_viewers(50000) == 100.0
        assert score_viewers(100000) == 100.0

    def test_high_tier(self):
        assert score_viewers(10000) == 80.0

    def test_mid_tier(self):
        assert score_viewers(5000) == 60.0

    def test_low_tier(self):
        assert score_viewers(100) == 20.0
        assert score_viewers(0) == 0.0

    def test_boundary(self):
        assert score_viewers(99) == 0.0
        assert score_viewers(100) == 20.0
        assert score_viewers(1000) == 40.0


# ── Rules: score_price ───────────────────────────────────────


class TestScorePrice:
    """5 groups for price scoring."""

    def test_optimal_range(self):
        """¥50-300 should score 80-100."""
        score = score_price(175.0)  # center
        assert 95.0 <= score <= 100.0
        assert score_price(50.0) == 80.0
        assert score_price(300.0) == 80.0

    def test_below_optimal(self):
        """Below ¥50: lower price → lower score."""
        assert score_price(25.0) == 40.0
        assert score_price(1.0) == pytest.approx(1.6, abs=0.1)

    def test_above_optimal(self):
        """Above ¥300: higher price → lower score."""
        score = score_price(2650.0)
        assert 0.0 < score < 80.0

    def test_extreme_prices(self):
        """Very high or zero/negative price → 0."""
        assert score_price(5000.0) == 0.0
        assert score_price(10000.0) == 0.0
        assert score_price(0.0) == 0.0
        assert score_price(-10.0) == 0.0

    def test_boundary_prices(self):
        assert score_price(49.9) < 80.0
        assert score_price(50.0) == 80.0
        assert score_price(300.1) < 80.0


# ── Rules: calculate_score ────────────────────────────────────


class TestCalculateScore:
    """Composite score tests."""

    def test_max_score(self):
        """Best case: high sales + high viewers + optimal price."""
        score = calculate_score(sales=10000, viewers=50000, price=175.0)
        assert score >= 90.0

    def test_min_score(self):
        """Worst case: zero everything."""
        score = calculate_score(sales=0, viewers=0, price=0.0)
        assert score == 0.0

    def test_score_range(self):
        """Score should always be 0-100."""
        score = calculate_score(sales=1000, viewers=5000, price=99.0)
        assert 0.0 <= score <= 100.0

    def test_weights_applied(self):
        """Verify weights are applied correctly."""
        # Only sales contributes (others are 0)
        s1 = calculate_score(sales=10000, viewers=0, price=0.0)
        assert s1 == pytest.approx(100.0 * 0.4, abs=0.1)


# ── ProductScorer ─────────────────────────────────────────────


class TestProductScorer:
    def test_score_method(self):
        scorer = ProductScorer()
        score = scorer.score(sales_24h=5000, viewers=10000, price=150.0)
        assert 0.0 <= score <= 100.0
        assert isinstance(score, float)

    def test_score_product(self):
        scorer = ProductScorer()
        product = _make_product(sales_24h=10000, viewers=50000, price=150.0)
        score = scorer.score_product(product)
        assert score >= 90.0

    def test_breakdown(self):
        scorer = ProductScorer()
        result = scorer.breakdown(sales_24h=5000, viewers=10000, price=150.0)
        assert "sales" in result
        assert "viewers" in result
        assert "price" in result
        assert "total" in result
        assert result["sales"] == 80.0
        assert result["viewers"] == 80.0
        assert result["total"] == pytest.approx(
            result["sales"] * 0.4 + result["viewers"] * 0.35 + result["price"] * 0.25,
            abs=0.01,
        )


# ── ProductAnalyzer ───────────────────────────────────────────


class TestProductAnalyzer:
    def _make_batch(self) -> list[CleanedProduct]:
        return [
            _make_product(name="爆款手机壳", sales_24h=10000, viewers=50000, price=99.0),
            _make_product(name="普通水杯", sales_24h=50, viewers=200, price=29.0),
            _make_product(name="高端耳机", sales_24h=5000, viewers=10000, price=299.0),
            _make_product(name="冷门凉席", sales_24h=5, viewers=30, price=199.0),
        ]

    def test_analyze(self):
        analyzer = ProductAnalyzer()
        results = analyzer.analyze(self._make_batch())
        assert len(results) == 4
        for r in results:
            assert "product" in r
            assert "ai_score" in r
            assert "breakdown" in r
            assert 0.0 <= r["ai_score"] <= 100.0

    def test_rank(self):
        analyzer = ProductAnalyzer()
        ranked = analyzer.rank(self._make_batch())
        scores = [r["ai_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)
        # Best product should be the 爆款手机壳
        assert ranked[0]["product"].name == "爆款手机壳"

    def test_top_hits(self):
        analyzer = ProductAnalyzer()
        top = analyzer.top_hits(self._make_batch(), n=2)
        assert len(top) == 2
        assert top[0]["ai_score"] >= top[1]["ai_score"]

    def test_top_hits_min_score(self):
        analyzer = ProductAnalyzer()
        top = analyzer.top_hits(self._make_batch(), n=10, min_score=50.0)
        for r in top:
            assert r["ai_score"] >= 50.0

    def test_summary(self):
        analyzer = ProductAnalyzer()
        stats = analyzer.summary(self._make_batch())
        assert stats["count"] == 4
        assert 0.0 <= stats["avg_score"] <= 100.0
        assert stats["max_score"] >= stats["avg_score"]
        assert stats["min_score"] <= stats["avg_score"]
        assert sum(stats["score_distribution"].values()) == 4

    def test_summary_empty(self):
        analyzer = ProductAnalyzer()
        stats = analyzer.summary([])
        assert stats["count"] == 0
        assert stats["avg_score"] == 0.0
