"""Tests for Phase 35: OpportunityScorer v2 — 商品机会评分.

Covers:
- 高利润 / 低利润商品
- 高匹配 / 无匹配商品
- 商品热度 (viewers + sales_24h)
- 供应竞争 (supplier count)
- 风险评估 (match quality, margin anomaly)
- 边界情况
- 分数排序
- 推荐等级
- dict 和 ORM 输入兼容
"""

from __future__ import annotations

import pytest

from app.services.opportunity.scorer import OpportunityScorer


# ── Helpers ──────────────────────────────────────────────────


class FakeProduct:
    """ORM-like product for testing."""
    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "测试商品")
        self.price = kwargs.get("price", 99.0)
        self.viewers = kwargs.get("viewers", 0)
        self.sales_24h = kwargs.get("sales_24h", 0)
        self.shop = kwargs.get("shop", "测试店铺")
        self.platform = kwargs.get("platform", "taobao")


class FakeMatch:
    """ORM-like match for testing."""
    def __init__(self, **kwargs):
        self.final_score = kwargs.get("final_score", 0.0)
        self.profit_margin = kwargs.get("profit_margin", 0.0)
        self.title = kwargs.get("title", "匹配商品")
        self.similarity_score = kwargs.get("similarity_score", self.final_score)


def _make_match_dict(
    final_score: float = 0.85,
    profit_margin: float = 50.0,
    title: str = "坚果礼盒 厂家直销",
) -> dict:
    return {
        "final_score": final_score,
        "profit_margin": profit_margin,
        "title": title,
        "similarity_score": final_score,
    }


def _make_product_dict(
    price: float = 99.0,
    viewers: int = 1000,
    sales_24h: int = 100,
    name: str = "测试商品",
) -> dict:
    return {
        "name": name,
        "price": price,
        "viewers": viewers,
        "sales_24h": sales_24h,
        "shop": "测试店铺",
    }


# ═══════════════════════════════════════════════════════════════
# Basic Scoring
# ═══════════════════════════════════════════════════════════════


class TestBasicScoring:
    """Basic calculation correctness."""

    def test_calculate_returns_all_keys(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=2000, sales_24h=50)
        matches = [_make_match_dict(0.85, 50.0)]
        result = scorer.calculate(product, matches)

        expected_keys = {
            "score", "match_score", "profit_score",
            "trend_score", "competition_score", "risk_score", "reasons",
        }
        assert set(result.keys()) == expected_keys

    def test_calculate_score_in_range(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=1000, sales_24h=100)
        matches = [_make_match_dict(0.85, 50.0)]
        result = scorer.calculate(product, matches)

        assert 0 <= result["score"] <= 100
        for key in ("match_score", "profit_score", "trend_score",
                     "competition_score", "risk_score"):
            assert 0 <= result[key] <= 100, f"{key} out of range: {result[key]}"

    def test_calculate_no_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=500, sales_24h=20)
        result = scorer.calculate(product, [])

        assert result["match_score"] == 0.0
        assert result["profit_score"] == 0.0
        assert result["risk_score"] <= 20  # high risk
        assert result["score"] < 50

    def test_calculate_none_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        result = scorer.calculate(product, None)

        assert isinstance(result["score"], float)
        assert result["match_score"] == 0.0


# ═══════════════════════════════════════════════════════════════
# Match Score
# ═══════════════════════════════════════════════════════════════


class TestMatchScore:
    """Match confidence scoring."""

    def test_high_match_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.95, 60.0)]
        result = scorer.calculate(product, matches)
        assert result["match_score"] > 80

    def test_low_match_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.35, 20.0)]
        result = scorer.calculate(product, matches)
        assert result["match_score"] < 50

    def test_multiple_good_matches_boosts_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        single = [_make_match_dict(0.85, 50.0)]
        multiple = [
            _make_match_dict(0.85, 50.0),
            _make_match_dict(0.80, 45.0),
            _make_match_dict(0.75, 40.0),
            _make_match_dict(0.70, 35.0),
            _make_match_dict(0.65, 30.0),
        ]
        r1 = scorer.calculate(product, single)
        r2 = scorer.calculate(product, multiple)
        assert r2["match_score"] >= r1["match_score"]

    def test_matches_with_zero_final_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.0, 0.0)]
        result = scorer.calculate(product, matches)
        assert result["match_score"] == pytest.approx(0.0, abs=10)


# ═══════════════════════════════════════════════════════════════
# Profit Score
# ═══════════════════════════════════════════════════════════════


class TestProfitScore:
    """Profit margin scoring."""

    def test_high_profit_margin(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0)
        matches = [_make_match_dict(0.85, 80.0)]
        result = scorer.calculate(product, matches)
        assert result["profit_score"] > 80

    def test_medium_profit_margin(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0)
        matches = [_make_match_dict(0.85, 55.0)]
        result = scorer.calculate(product, matches)
        assert 50 < result["profit_score"] < 90

    def test_low_profit_margin(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0)
        matches = [_make_match_dict(0.85, 10.0)]
        result = scorer.calculate(product, matches)
        assert result["profit_score"] < 40

    def test_zero_profit_margin(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.85, 0.0)]
        result = scorer.calculate(product, matches)
        assert result["profit_score"] <= 10


# ═══════════════════════════════════════════════════════════════
# Trend Score
# ═══════════════════════════════════════════════════════════════


class TestTrendScore:
    """Trend/heat scoring based on viewers + sales_24h."""

    def test_high_viewers_and_sales(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=8000, sales_24h=600)
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert result["trend_score"] > 80

    def test_no_viewers_no_sales(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=0, sales_24h=0)
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert result["trend_score"] <= 20

    def test_only_viewers(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=3000, sales_24h=0)
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert result["trend_score"] > 30

    def test_only_sales(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=0, sales_24h=200)
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert result["trend_score"] > 20

    def test_moderate_trend(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=1000, sales_24h=50)
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert 30 < result["trend_score"] < 80


# ═══════════════════════════════════════════════════════════════
# Competition Score
# ═══════════════════════════════════════════════════════════════


class TestCompetitionScore:
    """Supplier competition scoring (inverted — fewer = better)."""

    def test_exclusive_supplier_high_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.85, 50.0)]
        result = scorer.calculate(product, matches)
        assert result["competition_score"] >= 80

    def test_many_suppliers_low_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [
            _make_match_dict(0.8, 50.0, f"供应商{i}") for i in range(1, 15)
        ]
        result = scorer.calculate(product, matches)
        assert result["competition_score"] <= 50

    def test_no_suppliers_zero_competition_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        result = scorer.calculate(product, [])
        assert result["competition_score"] == 0.0

    def test_competition_few_suppliers(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict() for _ in range(3)]
        result = scorer.calculate(product, matches)
        assert result["competition_score"] > 60


# ═══════════════════════════════════════════════════════════════
# Risk Score
# ═══════════════════════════════════════════════════════════════


class TestRiskScore:
    """Risk assessment (higher = lower risk)."""

    def test_low_risk_good_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [
            _make_match_dict(0.85, 60.0),
            _make_match_dict(0.80, 55.0),
            _make_match_dict(0.75, 50.0),
        ]
        result = scorer.calculate(product, matches)
        assert result["risk_score"] >= 80

    def test_high_risk_no_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        result = scorer.calculate(product, [])
        assert result["risk_score"] <= 20

    def test_risk_anomalous_margin(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=199.0)
        matches = [_make_match_dict(0.85, 95.0)]  # suspiciously high
        result = scorer.calculate(product, matches)
        # Should have some risk reduction due to anomalous margin
        assert result["risk_score"] < 90

    def test_single_point_failure_risk(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.85, 50.0)]
        result = scorer.calculate(product, matches)
        # Single supplier → moderate risk
        assert result["risk_score"] < 95

    def test_all_low_quality_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [
            _make_match_dict(0.35, 20.0),
            _make_match_dict(0.30, 15.0),
        ]
        result = scorer.calculate(product, matches)
        # Low quality → higher risk (lower score)
        assert result["risk_score"] < 70


# ═══════════════════════════════════════════════════════════════
# Composite Score
# ═══════════════════════════════════════════════════════════════


class TestCompositeScore:
    """Overall composite score and weight distribution."""

    def test_perfect_product_high_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=10000, sales_24h=1000)
        matches = [
            _make_match_dict(0.95, 80.0),
            _make_match_dict(0.90, 70.0),
            _make_match_dict(0.85, 65.0),
        ]
        result = scorer.calculate(product, matches)
        assert result["score"] > 70

    def test_terrible_product_low_score(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=9.9, viewers=0, sales_24h=0)
        matches = [_make_match_dict(0.20, 5.0)]
        result = scorer.calculate(product, matches)
        assert result["score"] < 40

    def test_weight_distribution_proper(self):
        """Verify that match_score has the highest weight (40%)."""
        scorer = OpportunityScorer()
        # Create product where each dimension pulls differently
        product = FakeProduct(price=99.0, viewers=5000, sales_24h=500)
        matches = [_make_match_dict(0.90, 70.0)]
        result = scorer.calculate(product, matches)

        # Composite should be dominated by match (40%) and profit (25%)
        expected_contribution = (
            result["match_score"] * 0.40
            + result["profit_score"] * 0.25
            + result["trend_score"] * 0.20
            + result["competition_score"] * 0.10
            + result["risk_score"] * 0.05
        )
        assert result["score"] == pytest.approx(
            round(min(expected_contribution, 100.0), 1)
        )

    def test_composite_max_100(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=199.0, viewers=50000, sales_24h=5000)
        matches = [
            _make_match_dict(1.0, 90.0),
            _make_match_dict(1.0, 80.0),
            _make_match_dict(1.0, 85.0),
            _make_match_dict(1.0, 75.0),
            _make_match_dict(1.0, 70.0),
            _make_match_dict(1.0, 65.0),
        ]
        result = scorer.calculate(product, matches)
        assert result["score"] <= 100.0


# ═══════════════════════════════════════════════════════════════
# Reasons
# ═══════════════════════════════════════════════════════════════


class TestReasons:
    """Reason output completeness and correctness."""

    def test_reasons_not_empty(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict()]
        result = scorer.calculate(product, matches)
        assert len(result["reasons"]) > 0
        assert all(isinstance(r, str) for r in result["reasons"])

    def test_reasons_include_all_dimensions(self):
        scorer = OpportunityScorer()
        product = FakeProduct(viewers=3000, sales_24h=100)
        matches = [_make_match_dict(0.90, 65.0)]
        result = scorer.calculate(product, matches)
        reasons_text = " ".join(result["reasons"])
        assert "匹配" in reasons_text
        assert "利润" in reasons_text
        assert "热度" in reasons_text
        assert "竞争" in reasons_text
        assert "风险" in reasons_text

    def test_no_match_reasons(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        result = scorer.calculate(product, [])
        reasons_text = " ".join(result["reasons"])
        assert "无匹配" in reasons_text


# ═══════════════════════════════════════════════════════════════
# Recommendation
# ═══════════════════════════════════════════════════════════════


class TestGetRecommendation:
    """get_recommendation static method."""

    def test_strong_recommend(self):
        assert OpportunityScorer.get_recommendation(95) == "★★★★★ 强烈推荐"
        assert OpportunityScorer.get_recommendation(90) == "★★★★★ 强烈推荐"

    def test_worth_studying(self):
        assert OpportunityScorer.get_recommendation(85) == "★★★★ 值得研究"
        assert OpportunityScorer.get_recommendation(75) == "★★★★ 值得研究"

    def test_observe(self):
        assert OpportunityScorer.get_recommendation(70) == "★★★ 观察"
        assert OpportunityScorer.get_recommendation(60) == "★★★ 观察"

    def test_skip(self):
        assert OpportunityScorer.get_recommendation(59) == "暂不推荐"
        assert OpportunityScorer.get_recommendation(0) == "暂不推荐"


# ═══════════════════════════════════════════════════════════════
# Product as Dict Input
# ═══════════════════════════════════════════════════════════════


class TestProductDictInput:
    """Verify dict-like product input works."""

    def test_product_as_dict(self):
        scorer = OpportunityScorer()
        product = _make_product_dict(price=129.0, viewers=5000, sales_24h=300)
        matches = [_make_match_dict(0.88, 55.0)]
        result = scorer.calculate(product, matches)
        assert 0 <= result["score"] <= 100
        assert result["trend_score"] > 50

    def test_product_as_fake_orm(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=79.0, viewers=800, sales_24h=30)
        matches = [_make_match_dict(0.78, 45.0)]
        result = scorer.calculate(product, matches)
        assert result["profit_score"] > 0
        assert result["trend_score"] > 0

    def test_match_as_fake_orm(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [FakeMatch(final_score=0.92, profit_margin=65.0)]
        result = scorer.calculate(product, matches)
        assert result["match_score"] > 70
        assert result["profit_score"] > 60


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_default_product_all_zeros(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=0.0, viewers=0, sales_24h=0)
        result = scorer.calculate(product, [])
        assert result["score"] < 30

    def test_very_high_price_product(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=9999.0, viewers=100, sales_24h=5)
        matches = [_make_match_dict(0.70, 90.0)]
        result = scorer.calculate(product, matches)
        assert 0 <= result["score"] <= 100

    def test_large_number_of_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [
            _make_match_dict(0.7 + i * 0.001, 30.0 + i * 0.5)
            for i in range(50)
        ]
        result = scorer.calculate(product, matches)
        assert result["match_score"] >= 0
        assert result["competition_score"] <= 40

    def test_score_ordering_better_product_higher(self):
        """A clearly better product should score higher than a worse one."""
        scorer = OpportunityScorer()

        # Good product
        good = FakeProduct(price=99.0, viewers=8000, sales_24h=500)
        good_matches = [
            _make_match_dict(0.92, 75.0),
            _make_match_dict(0.85, 60.0),
        ]

        # Bad product
        bad = FakeProduct(price=9.9, viewers=10, sales_24h=0)
        bad_matches = [_make_match_dict(0.25, 5.0)]

        r_good = scorer.calculate(good, good_matches)
        r_bad = scorer.calculate(bad, bad_matches)

        assert r_good["score"] > r_bad["score"], (
            f"Good={r_good['score']}, Bad={r_bad['score']}"
        )

    def test_matches_with_strange_final_scores(self):
        """Matches with final_score > 1.0 should be clamped properly."""
        scorer = OpportunityScorer()
        product = FakeProduct()
        # final_score > 1.0 (unusual but shouldn't crash)
        matches = [_make_match_dict(1.5, 50.0)]
        result = scorer.calculate(product, matches)
        assert result["match_score"] <= 100

    def test_matches_with_negative_margin(self):
        """Negative profit margin should get very low profit score."""
        scorer = OpportunityScorer()
        product = FakeProduct()
        matches = [_make_match_dict(0.80, -10.0)]
        result = scorer.calculate(product, matches)
        assert result["profit_score"] <= 10


# ═══════════════════════════════════════════════════════════════
# Scoring Consistency
# ═══════════════════════════════════════════════════════════════


class TestScoringConsistency:
    """Verify consistent behavior across multiple calls."""

    def test_repeated_calls_same_result(self):
        scorer = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=2000, sales_24h=100)
        matches = [_make_match_dict(0.85, 55.0)]

        r1 = scorer.calculate(product, matches)
        r2 = scorer.calculate(product, matches)

        assert r1["score"] == r2["score"]
        assert r1["match_score"] == r2["match_score"]
        assert r1["profit_score"] == r2["profit_score"]

    def test_different_scorer_instances_same_result(self):
        s1 = OpportunityScorer()
        s2 = OpportunityScorer()
        product = FakeProduct(price=99.0, viewers=2000, sales_24h=100)
        matches = [_make_match_dict(0.85, 55.0)]

        r1 = s1.calculate(product, matches)
        r2 = s2.calculate(product, matches)

        assert r1["score"] == r2["score"]

    def test_score_increases_with_better_matches(self):
        scorer = OpportunityScorer()
        product = FakeProduct()
        poor = [_make_match_dict(0.40, 20.0)]
        good = [_make_match_dict(0.90, 70.0)]

        r_poor = scorer.calculate(product, poor)
        r_good = scorer.calculate(product, good)

        assert r_good["match_score"] > r_poor["match_score"]
        assert r_good["profit_score"] > r_poor["profit_score"]

    def test_more_good_matches_increases_competition_but_lowers_risk(self):
        scorer = OpportunityScorer()
        product = FakeProduct()

        one = [_make_match_dict(0.85, 60.0)]
        many = [
            _make_match_dict(0.85, 60.0),
            _make_match_dict(0.80, 55.0),
            _make_match_dict(0.75, 50.0),
        ]

        r_one = scorer.calculate(product, one)
        r_many = scorer.calculate(product, many)

        # More good matches → lower competition_score (more crowded)
        assert r_many["competition_score"] < r_one["competition_score"]
        # More good matches → higher risk_score (lower risk)
        assert r_many["risk_score"] > r_one["risk_score"]
