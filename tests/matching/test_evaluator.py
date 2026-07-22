"""Tests for Phase 29: MatchingEvaluator."""

import pytest

from app.matching.evaluator import MatchingEvaluator


# ── Helpers ──────────────────────────────────────────────────

def _make_product(pid: str, title: str) -> dict:
    return {"id": pid, "title": title}


def _make_result(supplier_id: str, score: float = 0.9) -> dict:
    return {
        "supplier_product_id": supplier_id,
        "final_score": score,
        "text_score": 0.8,
        "feature_score": 0.5,
        "title": f"Supplier {supplier_id}",
        "price": 50.0,
        "url": f"https://example.com/{supplier_id}",
    }


class TestBasicEvaluation:
    """Test basic evaluator functionality."""

    def test_all_correct_top1(self):
        """100% top1 accuracy when all matches rank first."""
        evaluator = MatchingEvaluator()
        products = [
            _make_product("t1", "坚果礼盒"),
            _make_product("t2", "蓝牙耳机"),
        ]
        ground_truth = {"t1": "p1", "t2": "p2"}
        results_map = {
            "t1": [
                _make_result("p1", 0.95),
                _make_result("p2", 0.3),
            ],
            "t2": [
                _make_result("p2", 0.90),
                _make_result("p1", 0.2),
            ],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)

        assert result["total_count"] == 2
        assert result["matched_count"] == 2
        assert result["top1_accuracy"] == 1.0
        assert result["top3_accuracy"] == 1.0
        assert result["top10_accuracy"] == 1.0

    def test_correct_at_top3(self):
        """Correct match at top-3 but not top-1."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p1"}
        results_map = {
            "t1": [
                _make_result("p2", 0.8),
                _make_result("p3", 0.6),
                _make_result("p1", 0.5),
            ],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)

        assert result["top1_accuracy"] == 0.0
        assert result["top3_accuracy"] == 1.0
        assert result["top10_accuracy"] == 1.0

    def test_correct_only_at_top10(self):
        """Correct match at position 5 (top-10 but not top-3)."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p_target"}
        results_map = {
            "t1": [
                _make_result(f"p{i}", 0.9 - i * 0.05) for i in range(1, 11)
            ],
        }
        # Put correct match at position 5 (index 4)
        results_map["t1"][4] = _make_result("p_target", 0.7)

        result = evaluator.evaluate_sync(products, ground_truth, results_map)

        assert result["top1_accuracy"] == 0.0
        assert result["top3_accuracy"] == 0.0
        assert result["top10_accuracy"] == 1.0

    def test_no_match_found(self):
        """Correct match not in results at all."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p_correct"}
        results_map = {
            "t1": [
                _make_result("p_wrong_1", 0.5),
                _make_result("p_wrong_2", 0.4),
            ],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)

        assert result["top1_accuracy"] == 0.0
        assert result["top3_accuracy"] == 0.0
        assert result["top10_accuracy"] == 0.0

    def test_mixed_accuracy(self):
        """Mixed results: some correct, some wrong."""
        evaluator = MatchingEvaluator()
        products = [
            _make_product("t1", "坚果礼盒"),
            _make_product("t2", "蓝牙耳机"),
            _make_product("t3", "手机壳"),
        ]
        ground_truth = {"t1": "p1", "t2": "p2", "t3": "p3"}
        results_map = {
            "t1": [_make_result("p1", 0.95)],  # Correct at top-1
            "t2": [
                _make_result("p_other", 0.7),  # p2 not found
            ],
            "t3": [
                _make_result("p_wrong", 0.6),
                _make_result("p3", 0.4),  # Correct at position 2
            ],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)

        assert result["matched_count"] == 3
        assert result["top1_accuracy"] == pytest.approx(1 / 3, abs=0.01)
        assert result["top3_accuracy"] == pytest.approx(2 / 3, abs=0.01)


class TestAvgScore:
    """Test average score calculation."""

    def test_avg_score_with_hits(self):
        """Average score should include correct match scores."""
        evaluator = MatchingEvaluator()
        products = [
            _make_product("t1", "A"),
            _make_product("t2", "B"),
        ]
        ground_truth = {"t1": "p1", "t2": "p2"}
        results_map = {
            "t1": [_make_result("p1", 0.9)],
            "t2": [_make_result("p2", 0.5)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["avg_score"] == pytest.approx(0.7, abs=0.01)

    def test_avg_score_miss_is_zero(self):
        """Missed matches contribute 0 to avg_score."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "A"), _make_product("t2", "B")]
        ground_truth = {"t1": "p1", "t2": "p2"}
        results_map = {
            "t1": [_make_result("p1", 0.9)],
            "t2": [_make_result("p_wrong", 0.5)],  # p2 not found
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["avg_score"] == pytest.approx(0.45, abs=0.01)


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_products(self):
        """Empty product list returns zeros."""
        evaluator = MatchingEvaluator()
        result = evaluator.evaluate_sync([], {}, {})
        assert result["total_count"] == 0
        assert result["top1_accuracy"] == 0.0

    def test_no_ground_truth(self):
        """Products with no ground truth are skipped."""
        evaluator = MatchingEvaluator()
        products = [
            _make_product("t1", "A"),
            _make_product("t2", "B"),
        ]
        ground_truth = {}  # No ground truth
        results_map = {
            "t1": [_make_result("p1", 0.9)],
            "t2": [_make_result("p2", 0.8)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["matched_count"] == 0
        assert result["top1_accuracy"] == 0.0

    def test_partial_ground_truth(self):
        """Only products with ground truth are evaluated."""
        evaluator = MatchingEvaluator()
        products = [
            _make_product("t1", "A"),
            _make_product("t2", "B"),
        ]
        ground_truth = {"t1": "p1"}  # Only t1 has ground truth
        results_map = {
            "t1": [_make_result("p1", 0.9)],
            "t2": [_make_result("p2", 0.8)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["matched_count"] == 1
        assert result["total_count"] == 2
        assert result["top1_accuracy"] == 1.0  # 1/1

    def test_empty_ground_truth_value(self):
        """Ground truth with empty string value is skipped."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "A"), _make_product("t2", "B")]
        ground_truth = {"t1": "", "t2": "p2"}
        results_map = {
            "t1": [_make_result("p1", 0.9)],
            "t2": [_make_result("p2", 0.8)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["matched_count"] == 1

    def test_results_empty(self):
        """Empty matcher results means no match."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "A")]
        ground_truth = {"t1": "p1"}
        results_map = {"t1": []}

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["top1_accuracy"] == 0.0
        assert result["avg_score"] == 0.0

    def test_supplier_id_type_coercion(self):
        """supplier_product_id comparison should handle int/str mismatch."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "1"}  # string
        results_map = {
            "t1": [
                {"supplier_product_id": 1, "final_score": 0.9},  # int
            ],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        assert result["top1_accuracy"] == 1.0


class TestDetailsOutput:
    """Test details field in output."""

    def test_details_contains_required_fields(self):
        """Each detail entry should have expected fields."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p1"}
        results_map = {
            "t1": [_make_result("p1", 0.9)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        details = result["details"]

        assert len(details) == 1
        d = details[0]
        assert d["product_id"] == "t1"
        assert d["title"] == "坚果"
        assert d["expected_supplier_id"] == "p1"
        assert d["found_rank"] == 1
        assert d["match_hit"] is True
        assert d["found_score"] == pytest.approx(0.9)

    def test_details_match_hit_false(self):
        """match_hit should be False when not found."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p_correct"}
        results_map = {
            "t1": [_make_result("p_wrong", 0.5)],
        }

        result = evaluator.evaluate_sync(products, ground_truth, results_map)
        d = result["details"][0]
        assert d["match_hit"] is False
        assert d["found_rank"] is None
        assert d["found_score"] == 0.0


class TestTopKParameter:
    """Test top_k parameter behavior."""

    def test_top_k_limits_results(self):
        """top_k parameter should cap the search depth."""
        evaluator = MatchingEvaluator()
        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p_correct"}
        results_map = {
            "t1": [
                _make_result(f"p{i}", 0.9 - i * 0.05) for i in range(1, 12)
            ],
        }
        # Put correct match at position 8 (index 7), overwrite existing
        results_map["t1"][7] = _make_result("p_correct", 0.55)

        # With top_k=5, position 8 is excluded → miss
        result_5 = evaluator.evaluate_sync(products, ground_truth, results_map, top_k=5)
        assert result_5["top10_accuracy"] == 0.0

        # With top_k=10, position 8 is included → hit
        result_10 = evaluator.evaluate_sync(products, ground_truth, results_map, top_k=10)
        assert result_10["top10_accuracy"] == 1.0


@pytest.mark.asyncio
class TestAsyncEvaluate:
    """Test async evaluate method."""

    async def test_async_basic(self):
        """Async evaluate should work with a simple matcher."""
        evaluator = MatchingEvaluator()

        async def mock_matcher(title: str, top_k: int) -> list[dict]:
            return [
                _make_result("p1", 0.95),
                _make_result("p2", 0.5),
            ]

        products = [_make_product("t1", "坚果")]
        ground_truth = {"t1": "p1"}

        result = await evaluator.evaluate(products, ground_truth, mock_matcher)
        assert result["top1_accuracy"] == 1.0

    async def test_async_empty(self):
        """Async evaluate with empty products."""
        evaluator = MatchingEvaluator()

        async def mock_matcher(title: str, top_k: int) -> list[dict]:
            return []

        result = await evaluator.evaluate([], {}, mock_matcher)
        assert result["total_count"] == 0
