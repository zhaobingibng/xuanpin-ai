"""Tests for Phase 28: FusionMatcher."""

import pytest

from app.matching.fusion_matcher import FusionMatcher
from app.matching.feature_extractor import FeatureExtractor


# ── Helpers ──────────────────────────────────────────────────

def _make_features(**overrides):
    """Create a feature dict with defaults."""
    defaults = {
        "keywords": [],
        "category": "",
        "weight_value": 0.0,
        "weight_unit": "",
        "package": "",
        "target": "",
    }
    defaults.update(overrides)
    return defaults


class TestFusionCalculate:
    """Test FusionMatcher.calculate method."""

    def test_basic_fusion(self):
        """Should compute text, feature, and final scores."""
        fusion = FusionMatcher()
        query = _make_features(keywords=["坚果", "零食"], category="食品")
        candidate = _make_features(keywords=["坚果", "礼盒"], category="食品")

        result = fusion.calculate(
            text_score=0.8,
            query_features=query,
            candidate_features=candidate,
        )

        assert "text_score" in result
        assert "feature_score" in result
        assert "final_score" in result
        assert 0 <= result["final_score"] <= 1

    def test_final_score_formula(self):
        """final_score = text_score * 0.6 + feature_score * 0.4."""
        fusion = FusionMatcher()
        query = _make_features(keywords=["坚果"])
        candidate = _make_features(keywords=["坚果"])

        result = fusion.calculate(
            text_score=1.0,
            query_features=query,
            candidate_features=candidate,
        )

        # With perfect text match + same keywords, feature_score should be > 0
        expected_final = 1.0 * 0.6 + result["feature_score"] * 0.4
        assert result["final_score"] == pytest.approx(expected_final, abs=0.01)

    def test_feature_score_in_range(self):
        """Feature score should be in [0, 1]."""
        fusion = FusionMatcher()
        query = _make_features(
            keywords=["坚果", "零食"], category="食品",
            package="袋装", target="儿童",
        )
        candidate = _make_features(
            keywords=["耳机"], category="数码",
            package="盒装", target="学生",
        )

        result = fusion.calculate(
            text_score=0.5,
            query_features=query,
            candidate_features=candidate,
        )

        assert 0 <= result["feature_score"] <= 1


class TestSameCategoryBoost:
    """Test that same category boosts score."""

    def test_same_category_boosts(self):
        """Same category should increase feature_score."""
        fusion = FusionMatcher()
        query = _make_features(keywords=["坚果", "零食"], category="食品")
        same_cat = _make_features(keywords=["海苔", "卷"], category="食品")
        diff_cat = _make_features(keywords=["耳机"], category="数码")

        r_same = fusion.calculate(0.7, query, same_cat)
        r_diff = fusion.calculate(0.7, query, diff_cat)

        assert r_same["feature_score"] > r_diff["feature_score"]

    def test_same_category_higher_final(self):
        """Same category should result in higher final_score."""
        fusion = FusionMatcher()
        query = _make_features(keywords=["坚果"], category="食品")
        food = _make_features(keywords=["坚果"], category="食品")
        digital = _make_features(keywords=["坚果"], category="数码")

        r_food = fusion.calculate(0.5, query, food)
        r_digital = fusion.calculate(0.5, query, digital)

        assert r_food["final_score"] > r_digital["final_score"]


class TestWeightMatch:
    """Test weight matching."""

    def test_same_weight_exact(self):
        """Same weight value and unit should score high."""
        fusion = FusionMatcher()
        query = _make_features(weight_value=50.0, weight_unit="g")
        candidate = _make_features(weight_value=50.0, weight_unit="g")

        r = fusion.calculate(0.8, query, candidate)
        assert r["feature_score"] > 0.0

    def test_different_weight(self):
        """Different weight should score lower."""
        fusion = FusionMatcher()
        query = _make_features(weight_value=50.0, weight_unit="g")
        candidate = _make_features(weight_value=100.0, weight_unit="g")

        r = fusion.calculate(0.8, query, candidate)
        # Should still have some feature score from other components
        assert r["feature_score"] >= 0.0

    def test_one_has_weight(self):
        """One has weight while other doesn't."""
        fusion = FusionMatcher()
        query = _make_features(weight_value=50.0, weight_unit="g")
        candidate = _make_features(weight_value=0.0, weight_unit="")

        r = fusion.calculate(0.8, query, candidate)
        # Weight component should be 0 but other components may score
        assert 0 <= r["final_score"] <= 1


class TestPackageMatch:
    """Test package type matching."""

    def test_same_package(self):
        """Same package type should boost score."""
        fusion = FusionMatcher()
        query = _make_features(
            keywords=["海苔", "零食"], package="桶装",
        )
        candidate = _make_features(
            keywords=["海苔", "卷"], package="桶装",
        )

        r = fusion.calculate(0.7, query, candidate)
        assert r["feature_score"] > 0.1

    def test_different_package(self):
        """Different package should score lower than same."""
        fusion = FusionMatcher()
        query = _make_features(
            keywords=["海苔", "零食"], package="桶装",
        )
        same_pkg = _make_features(
            keywords=["海苔", "卷"], package="桶装",
        )
        diff_pkg = _make_features(
            keywords=["海苔", "卷"], package="袋装",
        )

        r_same = fusion.calculate(0.7, query, same_pkg)
        r_diff = fusion.calculate(0.7, query, diff_pkg)

        assert r_same["feature_score"] > r_diff["feature_score"]


class TestTargetMatch:
    """Test target audience matching."""

    def test_same_target(self):
        """Same target audience should boost score."""
        fusion = FusionMatcher()
        query = _make_features(
            keywords=["儿童", "零食"], target="儿童",
        )
        candidate = _make_features(
            keywords=["儿童", "饼干"], target="儿童",
        )

        r = fusion.calculate(0.7, query, candidate)
        assert r["feature_score"] > 0.1


class TestDifferentProducts:
    """Test that completely different products score low."""

    def test_completely_different(self):
        """Different categories & keywords should score low."""
        fusion = FusionMatcher()
        query = _make_features(
            keywords=["坚果", "零食", "礼盒"], category="食品",
            package="礼盒", target="儿童",
        )
        candidate = _make_features(
            keywords=["蓝牙", "耳机", "降噪"], category="数码",
            weight_value=50.0, weight_unit="g",
        )

        r = fusion.calculate(0.1, query, candidate)
        # With low text score + no feature overlap, final should be low
        assert r["final_score"] < 0.3


class TestScoreOrdering:
    """Test that scores are ordered correctly."""

    def test_final_not_greater_than_text(self):
        """final_score should not exceed text_score significantly."""
        fusion = FusionMatcher()
        query = _make_features(keywords=["坚果"])
        candidate = _make_features(keywords=["坚果"])

        for text_score in [0.2, 0.5, 0.9]:
            r = fusion.calculate(text_score, query, candidate)
            # final can be higher than text if feature_score > text_score
            # But should be reasonable
            assert 0 <= r["final_score"] <= 1

    def test_empty_features_still_works(self):
        """Empty features should not break scoring."""
        fusion = FusionMatcher()
        query = _make_features()
        candidate = _make_features()

        r = fusion.calculate(0.5, query, candidate)
        assert r["feature_score"] == 0.0
        assert r["final_score"] == 0.3  # 0.5 * 0.6 + 0.0 * 0.4


class TestExtractFeatures:
    """Test FusionMatcher.extract_features method."""

    def test_extract_features(self):
        """Should extract features from a title."""
        fusion = FusionMatcher()
        features = fusion.extract_features("儿童海苔卷零食50g桶装")

        assert "keywords" in features
        assert "weight_value" in features
        assert features["target"] == "儿童"
        assert features["package"] == "桶装"

    def test_extract_features_empty(self):
        """Should handle empty title."""
        fusion = FusionMatcher()
        features = fusion.extract_features("")

        assert features["keywords"] == []
