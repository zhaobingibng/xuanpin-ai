"""Tests for Phase 31: EvaluationReport — 真实商品匹配效果评估报告."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.matching.evaluation_report import EvaluationReport, _calc_profit_margin


# ── Helpers ──────────────────────────────────────────────────

def _make_eval_item(title: str, price: float, correct_id: int | None, notes: str = "") -> dict:
    """Create an evaluation data entry."""
    item: dict = {
        "title": title,
        "price": price,
        "correct_supplier_product_id": correct_id,
    }
    if notes:
        item["notes"] = notes
    return item


def _make_match_result(
    supplier_id: int,
    final_score: float = 0.9,
    title: str = "",
    price: float = 50.0,
) -> dict:
    """Create a simulated ProductMatcher result dict."""
    return {
        "supplier_product_id": supplier_id,
        "final_score": final_score,
        "text_score": 0.8,
        "feature_score": 0.6,
        "title": title or f"Supplier {supplier_id}",
        "price": price,
        "url": f"https://example.com/{supplier_id}",
        "offer_id": f"offer_{supplier_id}",
        "shop_name": f"Shop {supplier_id}",
    }


# ── Test: _calc_profit_margin helper ─────────────────────────

class TestCalcProfitMargin:
    """Test _calc_profit_margin utility function."""

    def test_normal_profit(self):
        """Sell 100, cost 60 → 40% margin."""
        assert _calc_profit_margin(100.0, 60.0) == 40.0

    def test_breakeven(self):
        """Sell 100, cost 100 → 0% margin."""
        assert _calc_profit_margin(100.0, 100.0) == 0.0

    def test_loss(self):
        """Sell 80, cost 100 → -25%."""
        assert _calc_profit_margin(80.0, 100.0) == -25.0

    def test_zero_price(self):
        """Sell price 0 → margin 0."""
        assert _calc_profit_margin(0.0, 50.0) == 0.0

    def test_negative_price(self):
        """Sell price negative → margin 0."""
        assert _calc_profit_margin(-10.0, 50.0) == 0.0

    def test_high_margin(self):
        """Sell 200, cost 20 → 90%."""
        assert _calc_profit_margin(200.0, 20.0) == 90.0


# ── Test: generate_sync — basic accuracy ─────────────────────

class TestGenerateSyncAccuracy:
    """Test accuracy metrics in generate_sync."""

    def test_all_correct_top1(self):
        """All correct at rank 1 → 100% accuracy."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("坚果礼盒", 99.0, 1),
            _make_eval_item("蓝牙耳机", 59.0, 2),
        ]
        results_map = {
            "坚果礼盒": [
                _make_match_result(1, 0.95, price=70.0),
                _make_match_result(3, 0.30, price=50.0),
            ],
            "蓝牙耳机": [
                _make_match_result(2, 0.90, price=30.0),
                _make_match_result(4, 0.20, price=50.0),
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)

        s = report["summary"]
        assert s["total"] == 2
        assert s["labeled_count"] == 2
        assert s["top1_accuracy"] == 1.0
        assert s["top3_accuracy"] == 1.0
        assert s["top10_recall"] == 1.0

    def test_correct_at_top3_not_top1(self):
        """Correct at rank 3 → top1=0, top3=1."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 99.0, 1)]
        results_map = {
            "坚果": [
                _make_match_result(2, 0.8, price=50.0),
                _make_match_result(3, 0.7, price=50.0),
                _make_match_result(1, 0.6, price=70.0),
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["summary"]["top3_accuracy"] == 1.0

    def test_correct_at_top8_only(self):
        """Correct at rank 8 → top10_recall=1 but top3=0."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("手机壳", 29.9, 10)]
        results = [
            _make_match_result(i, 0.95 - i * 0.02) for i in range(1, 11)
        ]
        # Put correct at position 8
        results[7] = _make_match_result(10, 0.6, price=20.0)

        results_map = {"手机壳": results}
        report = report_gen.generate_sync(eval_data, results_map, top_k=10)
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["summary"]["top3_accuracy"] == 0.0
        assert report["summary"]["top10_recall"] == 1.0

    def test_no_match_found(self):
        """Correct supplier_id not in results → all zeros."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 99.0, 1)]
        results_map = {
            "坚果": [
                _make_match_result(99, 0.5, price=50.0),
                _make_match_result(88, 0.4, price=50.0),
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["summary"]["top3_accuracy"] == 0.0
        assert report["summary"]["top10_recall"] == 0.0

    def test_mixed_accuracy(self):
        """Mixed: 2/3 correct at top-1, 3/3 at top-3."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),
            _make_eval_item("B", 50.0, 2),
            _make_eval_item("C", 30.0, 3),
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=70.0)],      # top-1 hit
            "B": [
                _make_match_result(99, 0.7, price=30.0),          # miss
            ],
            "C": [
                _make_match_result(88, 0.6, price=20.0),
                _make_match_result(3, 0.5, price=15.0),           # top-2 hit
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["labeled_count"] == 3
        assert report["summary"]["top1_accuracy"] == pytest.approx(1 / 3, abs=0.01)
        assert report["summary"]["top3_accuracy"] == pytest.approx(2 / 3, abs=0.01)
        assert report["summary"]["top10_recall"] == pytest.approx(2 / 3, abs=0.01)


# ── Test: generate_sync — profit metrics ─────────────────────

class TestGenerateSyncProfit:
    """Test profit-related output in generate_sync."""

    def test_profit_margin_calculation(self):
        """Avg profit margin should be correct for matched items."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),  # sell 100, cost 60 → 40%
            _make_eval_item("B", 80.0, 2),   # sell 80, cost 40 → 50%
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(2, 0.8, price=40.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["avg_profit_margin"] == 45.0

    def test_avg_final_score(self):
        """Avg final_score should be correct."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),
            _make_eval_item("B", 80.0, 2),
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=70.0)],
            "B": [_make_match_result(2, 0.5, price=40.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["avg_final_score"] == pytest.approx(0.7, abs=0.01)

    def test_miss_excluded_from_profit_avg(self):
        """Missed items should NOT affect avg_profit_margin."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),  # hit, 40%
            _make_eval_item("B", 80.0, 2),   # miss
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(99, 0.5, price=30.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        # Only A contributes to profit avg
        assert report["summary"]["avg_profit_margin"] == 40.0
        # But B contributes 0 to avg_score
        assert report["summary"]["avg_final_score"] == pytest.approx(0.45, abs=0.01)


# ── Test: generate_sync — profit distribution ────────────────

class TestProfitDistribution:
    """Test profit_distribution buckets."""

    def test_bucket_normal(self):
        """Two items in different buckets."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),  # 40%
            _make_eval_item("B", 80.0, 2),   # 50%
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(2, 0.8, price=40.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        buckets = report["profit_distribution"]
        assert buckets["40-60%"] == 2

    def test_bucket_loss(self):
        """Negative margin goes to <0%."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("A", 50.0, 1)]  # sell 50, cost 100 → -100%
        results_map = {"A": [_make_match_result(1, 0.9, price=100.0)]}

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["profit_distribution"]["<0%"] == 1

    def test_bucket_high_margin(self):
        """>60% margin."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("A", 100.0, 1)]
        results_map = {"A": [_make_match_result(1, 0.9, price=10.0)]}

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["profit_distribution"][">60%"] == 1

    def test_missed_items_not_bucketed(self):
        """Missed items should not appear in profit distribution."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),
            _make_eval_item("B", 80.0, 2),  # miss
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(99, 0.3, price=30.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        total_bucketed = sum(report["profit_distribution"].values())
        assert total_bucketed == 1  # only A


# ── Test: missed cases ───────────────────────────────────────

class TestMissedCases:
    """Test missed_cases field."""

    def test_missed_case_tracked(self):
        """Missed cases should appear in the report."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("坚果礼盒", 99.0, 1, notes="应匹配坚果类"),
        ]
        results_map = {
            "坚果礼盒": [_make_match_result(99, 0.5, price=50.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["missed_count"] == 1
        assert len(report["missed_cases"]) == 1
        assert report["missed_cases"][0]["title"] == "坚果礼盒"
        assert report["missed_cases"][0]["notes"] == "应匹配坚果类"

    def test_no_missed_when_all_correct(self):
        """No missed when all items match."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("A", 100.0, 1)]
        results_map = {"A": [_make_match_result(1, 0.9, price=60.0)]}

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["missed_count"] == 0


# ── Test: edge cases ─────────────────────────────────────────

class TestEdgeCases:
    """Test edge case handling."""

    def test_empty_eval_data(self):
        """Empty evaluation data → empty report."""
        report_gen = EvaluationReport()
        report = report_gen.generate_sync([], {})
        assert report["summary"]["total"] == 0
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["details"] == []

    def test_no_labeled_items(self):
        """Items without correct_supplier_product_id are skipped."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, None),   # no label
            _make_eval_item("B", 80.0, None),    # no label
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(2, 0.8, price=40.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["labeled_count"] == 0
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["summary"]["top3_accuracy"] == 0.0
        assert report["summary"]["top10_recall"] == 0.0
        assert report["summary"]["avg_profit_margin"] == 0.0

    def test_some_labeled_some_not(self):
        """Mixed labeled/unlabeled — only labeled count for metrics."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, 1),   # labeled, hit
            _make_eval_item("B", 80.0, None),  # unlabeled
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
            "B": [_make_match_result(2, 0.8, price=40.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["total"] == 2
        assert report["summary"]["labeled_count"] == 1
        assert report["summary"]["top1_accuracy"] == 1.0

    def test_empty_title_skipped(self):
        """Empty title items are skipped."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("", 100.0, 1),
            _make_eval_item("有效标题", 80.0, 2),
        ]
        results_map = {
            "有效标题": [_make_match_result(2, 0.9, price=50.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["total"] == 1  # only "有效标题"

    def test_empty_results(self):
        """Empty matcher results → miss."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 99.0, 1)]
        results_map = {"坚果": []}

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["top1_accuracy"] == 0.0
        assert report["summary"]["avg_final_score"] == 0.0

    def test_supplier_id_type_mismatch(self):
        """str vs int supplier_product_id should be handled."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 99.0, 1)]  # int
        results_map = {
            "坚果": [
                {"supplier_product_id": 1, "final_score": 0.9, "price": 70.0,
                 "title": "坚果", "text_score": 0.8, "feature_score": 0.6},
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert report["summary"]["top1_accuracy"] == 1.0

    def test_match_even_when_unlabeled(self):
        """Unlabeled items get details but don't affect accuracy."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("A", 100.0, None),
        ]
        results_map = {
            "A": [_make_match_result(1, 0.9, price=60.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        assert len(report["details"]) == 1
        # Unlabeled => no match_hit tracking needed (correct_id is None)
        d = report["details"][0]
        assert d["match_hit"] is False
        assert d["correct_supplier_product_id"] is None


# ── Test: details structure ──────────────────────────────────

class TestDetailsStructure:
    """Test detail entry fields."""

    def test_details_contains_expected_fields(self):
        """Each detail should have title, price, correct_id, etc."""
        report_gen = EvaluationReport()
        eval_data = [
            _make_eval_item("坚果礼盒", 99.0, 1, notes="测试备注"),
        ]
        results_map = {
            "坚果礼盒": [_make_match_result(1, 0.92, title="坚果礼盒大包装", price=70.0)],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        d = report["details"][0]
        assert d["title"] == "坚果礼盒"
        assert d["price"] == 99.0
        assert d["correct_supplier_product_id"] == 1
        assert d["notes"] == "测试备注"
        assert d["found_rank"] == 1
        assert d["found_score"] == 0.92
        assert d["found_price"] == 70.0
        assert d["match_hit"] is True

    def test_top_items_structure(self):
        """top_items should have rank, score, profit_margin."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 100.0, 1)]
        results_map = {
            "坚果": [
                _make_match_result(1, 0.9, title="坚果礼盒", price=60.0),
                _make_match_result(2, 0.5, title="零食礼包", price=50.0),
            ],
        }

        report = report_gen.generate_sync(eval_data, results_map)
        top_items = report["details"][0]["top_items"]
        assert len(top_items) == 2
        assert top_items[0]["rank"] == 1
        assert top_items[0]["title"] == "坚果礼盒"
        assert top_items[0]["profit_margin"] == 40.0  # (100-60)/100*100
        assert top_items[1]["profit_margin"] == 50.0  # (100-50)/100*100

    def test_top_items_capped_at_5(self):
        """top_items should have at most 5 entries."""
        report_gen = EvaluationReport()
        eval_data = [_make_eval_item("坚果", 100.0, 1)]
        results_map = {
            "坚果": [_make_match_result(i, 0.9 - i * 0.05) for i in range(1, 11)],
        }

        report = report_gen.generate_sync(eval_data, results_map, top_k=10)
        assert len(report["details"][0]["top_items"]) == 5


# ── Test: report structure ───────────────────────────────────

class TestReportStructure:
    """Test overall report structure."""

    def test_summary_required_keys(self):
        """Report summary should contain all required keys."""
        report_gen = EvaluationReport()
        report = report_gen.generate_sync([], {})
        expected_keys = {
            "total", "labeled_count",
            "top1_accuracy", "top3_accuracy", "top10_recall",
            "avg_final_score", "avg_profit_margin",
        }
        assert set(report["summary"].keys()) == expected_keys

    def test_report_top_level_keys(self):
        """Report should have summary, details, profit_distribution, missed fields."""
        report_gen = EvaluationReport()
        report = report_gen.generate_sync([_make_eval_item("A", 100.0, 1)], {
            "A": [_make_match_result(1, 0.9, price=60.0)],
        })
        expected_keys = {
            "summary", "details", "profit_distribution",
            "missed_count", "missed_cases",
        }
        assert set(report.keys()) == expected_keys

    def test_empty_report_keys(self):
        """Empty report should also have all keys."""
        report_gen = EvaluationReport()
        report = report_gen._empty_report()
        expected_keys = {
            "summary", "details", "profit_distribution",
            "missed_count", "missed_cases",
        }
        assert set(report.keys()) == expected_keys


# ── Test: generate (async) ───────────────────────────────────

@pytest.mark.asyncio
class TestGenerateAsync:
    """Test async generate with mocked ProductMatcher."""

    async def test_generate_async_basic(self):
        """Async generate should call ProductMatcher and produce report."""
        with patch(
            "app.matching.product_matcher.ProductMatcher",
            autospec=True,
        ) as mock_matcher:
            mock_instance = mock_matcher.return_value
            mock_instance.match_product.return_value = [
                _make_match_result(1, 0.95, price=70.0),
                _make_match_result(2, 0.3, price=50.0),
            ]

            mock_session = AsyncMock()

            report_gen = EvaluationReport()
            eval_data = [
                _make_eval_item("坚果礼盒", 99.0, 1),
                _make_eval_item("蓝牙耳机", 59.0, 2),
            ]

            report = await report_gen.generate(mock_session, eval_data, top_k=10)
            assert report["summary"]["total"] == 2
            assert mock_instance.match_product.call_count == 2

    async def test_generate_async_empty(self):
        """Async generate with empty data → empty report."""
        mock_session = AsyncMock()

        report_gen = EvaluationReport()
        report = await report_gen.generate(mock_session, [], top_k=10)
        assert report["summary"]["total"] == 0

    async def test_generate_async_match_error(self):
        """ProductMatcher exception → continue processing."""
        with patch(
            "app.matching.product_matcher.ProductMatcher",
            autospec=True,
        ) as mock_matcher:
            mock_instance = mock_matcher.return_value
            mock_instance.match_product.side_effect = Exception("DB error")

            mock_session = AsyncMock()

            report_gen = EvaluationReport()
            eval_data = [_make_eval_item("坚果", 99.0, 1)]

            report = await report_gen.generate(mock_session, eval_data, top_k=10)
            assert report["summary"]["total"] == 1
            assert report["missed_count"] == 1


# ── Test: generate_sync top_k parameter ──────────────────────

class TestTopKParameter:
    """Test top_k behavior in generate_sync."""

    def test_top_k_limits_search_depth(self):
        """top_k=3 limits search to 3 results."""
        report_gen = EvaluationReport()
        # correct_id=999 that only appears deep in results
        eval_data = [_make_eval_item("坚果", 99.0, 999)]
        results = [_make_match_result(i, 0.9 - i * 0.03) for i in range(1, 11)]
        # Put correct at position 5 (only place it appears)
        results[4] = _make_match_result(999, 0.75, price=70.0)

        results_map = {"坚果": results}

        # top_k=3 → miss (correct at position 5 truncated away)
        report_3 = report_gen.generate_sync(eval_data, results_map, top_k=3)
        assert report_3["summary"]["top10_recall"] == 0.0

        # top_k=10 → hit
        report_10 = report_gen.generate_sync(eval_data, results_map, top_k=10)
        assert report_10["summary"]["top10_recall"] == 1.0
