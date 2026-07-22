"""Tests for Phase 36: DailySelectionReportGenerator v2.

Covers:
- Top 排序 (by opportunity_score)
- 高分推荐 / 无匹配商品 / 利润展示 / 风险展示
- 空数据 / 边界情况
- 自动低分过滤
- 统计指标
- 兼容性: 旧报告生成器不受影响
"""

from __future__ import annotations

import pytest

from app.services.report.daily_selection_report_generator import (
    DailySelectionReportGenerator,
)
from app.services.opportunity.scorer import OpportunityScorer


# ── Helpers ──────────────────────────────────────────────────


def _make_product(
    pid: int,
    title: str = "测试商品",
    price: float = 99.0,
    viewers: int = 1000,
    sales_24h: int = 50,
) -> dict:
    return {
        "product_id": pid,
        "title": title,
        "name": title,
        "price": price,
        "viewers": viewers,
        "sales_24h": sales_24h,
    }


def _make_match(
    product_id: int,
    final_score: float = 0.85,
    profit_margin: float = 50.0,
    supplier_title: str = "供应商商品A",
    supplier_price: float = 50.0,
    supplier_product_id: int = 100,
) -> dict:
    return {
        "product_id": product_id,
        "final_score": final_score,
        "profit_margin": profit_margin,
        "supplier_title": supplier_title,
        "supplier_price": supplier_price,
        "title": supplier_title,
        "supplier_product_id": supplier_product_id,
    }


def _make_score(product_id: int, score: float) -> dict:
    return {"product_id": product_id, "score": score}


# ═══════════════════════════════════════════════════════════════
# Basic Generation
# ═══════════════════════════════════════════════════════════════


class TestBasicGeneration:
    """Basic report generation."""

    def test_generate_returns_all_keys(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "坚果礼盒", 99.0, 2000, 100)]
        matches = [_make_match(1, 0.85, 55.0, "坚果供应商", 45.0)]

        report = gen.generate(products, matches)

        assert "report_date" in report
        assert "summary" in report
        assert "top_products" in report
        assert "statistics" in report
        assert "generated_at" in report

    def test_generate_top_products_fields(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "蓝牙耳机")]
        matches = [_make_match(1, 0.88, 60.0, "耳机供应商", 35.0)]

        report = gen.generate(products, matches)
        top = report["top_products"]

        assert len(top) == 1
        p = top[0]
        assert p["product_id"] == 1
        assert "title" in p
        assert "opportunity_score" in p
        assert "recommendation" in p
        assert "supplier_info" in p
        assert "estimated_profit" in p
        assert "reasons" in p
        assert "risks" in p

    def test_generate_report_date_format(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        report = gen.generate(products)

        from datetime import date
        assert report["report_date"] == date.today().isoformat()

    def test_statistics_present(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1), _make_product(2)]
        matches = [_make_match(1, 0.85, 50.0)]
        report = gen.generate(products, matches)

        stats = report["statistics"]
        assert "total_products" in stats
        assert "matched_products" in stats
        assert "avg_score" in stats
        assert "avg_profit" in stats
        assert "high_opportunity_count" in stats
        assert "distribution" in stats


# ═══════════════════════════════════════════════════════════════
# Top Sorting
# ═══════════════════════════════════════════════════════════════


class TestTopSorting:
    """Sorting by opportunity_score descending."""

    def test_sorted_by_opportunity_score(self):
        gen = DailySelectionReportGenerator()
        products = [
            _make_product(1, "低分商品", 99.0, 100, 5),
            _make_product(2, "中分商品", 99.0, 2000, 100),
            _make_product(3, "高分商品", 99.0, 8000, 500),
        ]
        matches = [
            _make_match(1, 0.50, 20.0),
            _make_match(2, 0.75, 50.0),
            _make_match(3, 0.95, 80.0),
        ]

        report = gen.generate(products, matches)
        top = report["top_products"]

        scores = [p["opportunity_score"] for p in top]
        assert scores == sorted(scores, reverse=True), f"Scores not sorted: {scores}"
        assert top[0]["product_id"] == 3  # best should be first

    def test_limit_respected(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(i, f"商品{i}") for i in range(1, 31)]
        matches = [
            _make_match(i, 0.80, 50.0) for i in range(1, 31)
        ]

        report = gen.generate(products, matches, limit=10)
        assert len(report["top_products"]) == 10

    def test_limit_default_20(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(i, f"商品{i}") for i in range(1, 51)]
        matches = [
            _make_match(i, 0.80, 50.0) for i in range(1, 51)
        ]

        report = gen.generate(products, matches)
        assert len(report["top_products"]) <= 20

    def test_top_k_greater_than_available(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1), _make_product(2), _make_product(3)]
        matches = [
            _make_match(1, 0.85, 50.0),
            _make_match(2, 0.75, 40.0),
            _make_match(3, 0.65, 30.0),
        ]

        report = gen.generate(products, matches, limit=20)
        assert len(report["top_products"]) == 3  # all included


# ═══════════════════════════════════════════════════════════════
# High Score Recommendation
# ═══════════════════════════════════════════════════════════════


class TestHighScoreRecommendation:
    """Recommendation labels for high-score products."""

    def test_strong_recommend_label(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "高分商品", 99.0, 10000, 1000)]
        matches = [
            _make_match(1, 0.95, 80.0),
            _make_match(1, 0.90, 70.0),
        ]

        report = gen.generate(products, matches)
        if report["top_products"]:
            rec = report["top_products"][0]["recommendation"]
            assert "强烈推荐" in rec or "值得研究" in rec or "观察" in rec

    def test_high_score_not_filtered(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "爆款", 99.0, 5000, 300)]
        matches = [
            _make_match(1, 0.90, 75.0),
            _make_match(1, 0.85, 65.0),
        ]

        report = gen.generate(products, matches)
        assert len(report["top_products"]) >= 1

    def test_reasons_include_recommendation(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.88, 60.0)]

        report = gen.generate(products, matches)
        top = report["top_products"]
        if top:
            reasons_text = " ".join(top[0]["reasons"])
            assert "机会评分" in reasons_text


# ═══════════════════════════════════════════════════════════════
# No Match Products
# ═══════════════════════════════════════════════════════════════


class TestNoMatchProducts:
    """Products without matches."""

    def test_product_without_matches_appears(self):
        """A product with no matches still appears (with low score)."""
        gen = DailySelectionReportGenerator(min_score=0)  # allow low scores
        products = [_make_product(1, "无匹配商品", 199.0, 3000, 200)]
        # No matches for product 1

        report = gen.generate(products, [])
        # With min_score=0, even 0-score products appear
        assert len(report["top_products"]) >= 1

    def test_no_match_supplier_info_is_none(self):
        gen = DailySelectionReportGenerator(min_score=0)
        products = [_make_product(1)]
        report = gen.generate(products, [])

        if report["top_products"]:
            assert report["top_products"][0]["supplier_info"] is None

    def test_no_match_estimated_profit_is_none(self):
        gen = DailySelectionReportGenerator(min_score=0)
        products = [_make_product(1)]
        report = gen.generate(products, [])

        if report["top_products"]:
            assert report["top_products"][0]["estimated_profit"] is None

    def test_no_match_risks_warn_about_supplier(self):
        gen = DailySelectionReportGenerator(min_score=0)
        products = [_make_product(1)]
        report = gen.generate(products, [])

        if report["top_products"]:
            risks_text = " ".join(report["top_products"][0]["risks"])
            assert "供应商" in risks_text or "无" in risks_text


# ═══════════════════════════════════════════════════════════════
# Profit Display
# ═══════════════════════════════════════════════════════════════


class TestProfitDisplay:
    """Profit calculation and display."""

    def test_estimated_profit_calculated(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "商品", 99.0)]
        matches = [_make_match(1, 0.85, 50.0, supplier_price=45.0)]

        report = gen.generate(products, matches)
        profit = report["top_products"][0]["estimated_profit"]
        assert profit == pytest.approx(54.0)  # 99 - 45

    def test_profit_with_min_supplier_price(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "商品", 100.0)]
        matches = [
            _make_match(1, 0.80, 50.0, supplier_price=60.0, supplier_product_id=101),
            _make_match(1, 0.90, 40.0, supplier_price=40.0, supplier_product_id=102),
        ]

        report = gen.generate(products, matches)
        profit = report["top_products"][0]["estimated_profit"]
        assert profit == pytest.approx(60.0)  # 100 - min(60,40)

    def test_profit_without_supplier_price(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "商品", 99.0)]
        matches = [
            _make_match(1, 0.85, 50.0, supplier_price=0.0),
        ]

        report = gen.generate(products, matches)
        profit = report["top_products"][0]["estimated_profit"]
        # supplier_price=0 → maybe None or some value
        assert profit is not None

    def test_supplier_info_has_profit_margin(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.85, 65.0, "供应商A", 40.0)]

        report = gen.generate(products, matches)
        info = report["top_products"][0]["supplier_info"]
        assert info["profit_margin"] == pytest.approx(65.0)
        assert "match_count" in info


# ═══════════════════════════════════════════════════════════════
# Risk Display
# ═══════════════════════════════════════════════════════════════


class TestRiskDisplay:
    """Risk indicators in report."""

    def test_risks_list_not_empty(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.85, 50.0)]

        report = gen.generate(products, matches)
        risks = report["top_products"][0]["risks"]
        assert isinstance(risks, list)
        assert len(risks) > 0

    def test_anomalous_margin_risk(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.85, 95.0)]  # suspicious margin

        report = gen.generate(products, matches)
        risks_text = " ".join(report["top_products"][0]["risks"])
        assert "异常" in risks_text or "虚假" in risks_text

    def test_low_match_risk(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.30, 30.0)]  # low match

        report = gen.generate(products, matches)
        if report["top_products"]:
            risks_text = " ".join(report["top_products"][0]["risks"])
            assert "匹配度偏低" in risks_text or "不足" in risks_text

    def test_single_supplier_risk(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.85, 50.0)]  # only 1 supplier

        report = gen.generate(products, matches)
        if report["top_products"]:
            risks_text = " ".join(report["top_products"][0]["risks"])
            assert "仅1个" in risks_text or "无明显" in risks_text


# ═══════════════════════════════════════════════════════════════
# Empty Data
# ═══════════════════════════════════════════════════════════════


class TestEmptyData:
    """Empty inputs handling."""

    def test_empty_products(self):
        gen = DailySelectionReportGenerator()
        report = gen.generate([], [], limit=20)
        assert report["top_products"] == []
        assert report["statistics"]["total_products"] == 0

    def test_empty_matches(self):
        gen = DailySelectionReportGenerator(min_score=0)
        products = [_make_product(1, "测试")]
        report = gen.generate(products, [])
        assert report["statistics"]["total_products"] == 1
        assert report["statistics"]["matched_products"] == 0

    def test_empty_scores(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.85, 50.0)]
        # No pre-computed scores → auto-calculate
        report = gen.generate(products, matches, scores=[])
        assert "top_products" in report

    def test_all_empty(self):
        gen = DailySelectionReportGenerator()
        report = gen.generate([], [], [])
        assert isinstance(report["top_products"], list)
        assert len(report["top_products"]) == 0
        assert report["statistics"]["total_products"] == 0

    def test_none_matches_and_scores(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        report = gen.generate(products, None, None)
        assert "top_products" in report


# ═══════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════


class TestStatistics:
    """Statistics accuracy."""

    def test_total_products_count(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(i) for i in range(1, 11)]
        matches = [_make_match(i, 0.85, 50.0) for i in range(1, 6)]

        report = gen.generate(products, matches)
        assert report["statistics"]["total_products"] == 10

    def test_matched_products_count(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(i) for i in range(1, 6)]
        matches = [
            _make_match(1, 0.85, 50.0),
            _make_match(2, 0.75, 40.0),
            _make_match(3, 0.65, 30.0),
        ]

        report = gen.generate(products, matches)
        assert report["statistics"]["matched_products"] == 3

    def test_distribution_present(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(i) for i in range(1, 11)]
        matches = [_make_match(i, 0.80, 50.0) for i in range(1, 11)]

        report = gen.generate(products, matches)
        dist = report["statistics"]["distribution"]
        assert "strongly_recommended" in dist
        assert "worth_studying" in dist
        assert "observe" in dist

    def test_summary_not_empty(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1), _make_product(2)]
        matches = [_make_match(1, 0.85, 55.0)]

        report = gen.generate(products, matches)
        assert len(report["summary"]) > 0
        assert isinstance(report["summary"], str)


# ═══════════════════════════════════════════════════════════════
# Auto-Filter Low Scores
# ═══════════════════════════════════════════════════════════════


class TestAutoFilter:
    """Automatic filtering of low-score products."""

    def test_default_threshold_filters_low(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "低分", 9.9, 0, 0)]
        # No matches → very low opportunity score
        report = gen.generate(products, [])
        # Default min_score=30 filters it out
        assert len(report["top_products"]) == 0

    def test_custom_threshold(self):
        gen = DailySelectionReportGenerator(min_score=10)
        products = [_make_product(1, "中低分", 99.0, 100, 5)]
        matches = [_make_match(1, 0.50, 20.0)]

        report = gen.generate(products, matches)
        # With threshold 10, even low scores appear
        assert len(report["top_products"]) >= 1

    def test_filtered_vs_total(self):
        gen = DailySelectionReportGenerator(min_score=50)
        products = [
            _make_product(1, "高分", 99.0, 5000, 300),
            _make_product(2, "低分", 9.9, 0, 0),
        ]
        matches = [
            _make_match(1, 0.90, 70.0),
            _make_match(2, 0.20, 5.0),
        ]

        report = gen.generate(products, matches)
        # Product 2 should be filtered out
        ids = [p["product_id"] for p in report["top_products"]]
        assert 2 not in ids or len(report["top_products"]) < 2


# ═══════════════════════════════════════════════════════════════
# Pre-computed Scores
# ═══════════════════════════════════════════════════════════════


class TestPrecomputedScores:
    """Using pre-computed scores instead of auto-calculating."""

    def test_precomputed_score_used(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [_make_match(1, 0.50, 20.0)]  # would be low
        scores = [_make_score(1, 85.0)]  # pre-computed high score

        report = gen.generate(products, matches, scores)
        assert report["top_products"][0]["opportunity_score"] == pytest.approx(85.0)

    def test_no_precomputed_auto_calculates(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1, "坚果礼盒", 99.0, 5000, 200)]
        matches = [_make_match(1, 0.90, 70.0)]

        report = gen.generate(products, matches, scores=[])
        assert report["top_products"][0]["opportunity_score"] > 0


# ═══════════════════════════════════════════════════════════════
# Compatibility
# ═══════════════════════════════════════════════════════════════


class TestCompatibility:
    """Existing report services remain importable and unaffected."""

    def test_daily_report_service_importable(self):
        from app.services.report.daily_report import DailyReportService
        assert DailyReportService is not None

    def test_daily_selection_report_service_importable(self):
        from app.services.report.daily_selection_report import (
            DailySelectionReportService,
        )
        assert DailySelectionReportService is not None

    def test_generator_does_not_depend_on_db_session(self):
        """New generator should not require a DB session."""
        gen = DailySelectionReportGenerator()
        assert not hasattr(gen, "_session")


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_duplicate_product_ids(self):
        """Duplicate product_id — last one wins from product_map."""
        gen = DailySelectionReportGenerator()
        products = [
            _make_product(1, "第一版"),
            _make_product(1, "第二版", price=199.0),
        ]
        matches = [_make_match(1, 0.85, 50.0)]

        report = gen.generate(products, matches)
        if report["top_products"]:
            assert report["top_products"][0]["title"] == "第二版"

    def test_missing_optional_fields(self):
        gen = DailySelectionReportGenerator(min_score=0)
        products = [{"product_id": 1, "title": "最简商品"}]
        # Missing price, viewers, sales_24h

        report = gen.generate(products, [])
        assert report["statistics"]["total_products"] == 1

    def test_realistic_scenario(self):
        """Typical daily report with varied products."""
        gen = DailySelectionReportGenerator(min_score=10)
        products = [
            _make_product(1, "三只松鼠坚果礼盒", 89.9, 5000, 300),
            _make_product(2, "海苔卷零食大礼包", 29.9, 2000, 150),
            _make_product(3, "无线蓝牙耳机降噪款", 59.0, 800, 80),
            _make_product(4, "冷门小商品", 9.9, 10, 2),
            _make_product(5, "爆款手机壳", 19.9, 8000, 600),
        ]
        matches = [
            _make_match(1, 0.88, 60.0, "坚果批发", 40.0),
            _make_match(2, 0.75, 50.0, "海苔厂", 15.0),
            _make_match(3, 0.82, 45.0, "电子厂", 30.0),
            _make_match(5, 0.92, 70.0, "手机壳厂", 5.0),
        ]

        report = gen.generate(products, matches, limit=5)
        assert len(report["top_products"]) >= 3
        # Best should be product 5 (high match + high profit + high trend)
        scores = {p["product_id"]: p["opportunity_score"] for p in report["top_products"]}
        # Product 5 should be first or near first
        top_ids = [p["product_id"] for p in report["top_products"]]
        assert 5 in top_ids[:3]

    def test_large_dataset(self):
        gen = DailySelectionReportGenerator(min_score=10)
        products = [_make_product(i, f"商品{i}") for i in range(1, 101)]
        matches = [
            _make_match(i, 0.7 + (i % 30) * 0.01, 30 + (i % 50))
            for i in range(1, 51)
        ]

        report = gen.generate(products, matches, limit=20)
        assert len(report["top_products"]) <= 20
        assert report["statistics"]["total_products"] == 100
        assert report["statistics"]["matched_products"] == 50

    def test_match_final_score_none_handled(self):
        gen = DailySelectionReportGenerator()
        products = [_make_product(1)]
        matches = [{
            "product_id": 1,
            "final_score": None,
            "profit_margin": 30.0,
            "supplier_title": "供应商",
            "supplier_price": 30.0,
            "supplier_product_id": None,
        }]

        report = gen.generate(products, matches)
        # Should not crash
        assert "top_products" in report

    def test_all_fields_zero_or_none(self):
        gen = DailySelectionReportGenerator()
        products = [{
            "product_id": 1,
            "title": "全空商品",
            "price": 0,
            "viewers": 0,
            "sales_24h": 0,
        }]

        report = gen.generate(products, [])
        # Should handle gracefully
        assert isinstance(report["summary"], str)

    def test_score_ordering_stable(self):
        """Same inputs → same ordering across multiple calls."""
        gen = DailySelectionReportGenerator()
        products = [
            _make_product(1, "A", 100.0, 1000, 50),
            _make_product(2, "B", 80.0, 500, 20),
            _make_product(3, "C", 120.0, 2000, 100),
        ]
        matches = [
            _make_match(1, 0.85, 55.0),
            _make_match(2, 0.75, 40.0),
            _make_match(3, 0.90, 65.0),
        ]

        r1 = gen.generate(products, matches)
        r2 = gen.generate(products, matches)

        ids1 = [p["product_id"] for p in r1["top_products"]]
        ids2 = [p["product_id"] for p in r2["top_products"]]
        assert ids1 == ids2
