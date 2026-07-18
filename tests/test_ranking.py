"""Tests for RankingService."""

import pytest

from app.models.product import Product
from app.services.ranking.ranking import RankingService


def _make_product(
    pid: int, name: str, platform: str = "抖音", price: float = 99.0,
) -> Product:
    """Create a lightweight Product instance for testing."""
    return Product(id=pid, name=name, platform=platform, shop="测试店铺", price=price)


def _make_items(data: list[tuple[int, str, float, float]]) -> list[dict]:
    """Build item list from compact data: (id, name, ai_score, trend_score)."""
    return [
        {"product": _make_product(pid, name), "ai_score": ai, "trend_score": tr}
        for pid, name, ai, tr in data
    ]


class TestRankingOrder:
    """Verify correct descending sort by final_score."""

    def test_highest_score_first(self):
        items = _make_items([
            (1, "商品A", 60.0, 40.0),  # final = 60*0.6 + 40*0.4 = 52.0
            (2, "商品B", 90.0, 80.0),  # final = 90*0.6 + 80*0.4 = 86.0
            (3, "商品C", 75.0, 60.0),  # final = 75*0.6 + 60*0.4 = 69.0
        ])
        board = RankingService().get_top_products(items)

        assert board[0]["rank"] == 1
        assert board[0]["name"] == "商品B"
        assert board[0]["final_score"] == 86.0

        assert board[1]["rank"] == 2
        assert board[1]["name"] == "商品C"

        assert board[2]["rank"] == 3
        assert board[2]["name"] == "商品A"

    def test_rank_assignment(self):
        items = _make_items([
            (1, "A", 90.0, 90.0),
            (2, "B", 80.0, 80.0),
            (3, "C", 70.0, 70.0),
        ])
        board = RankingService().get_top_products(items)
        ranks = [entry["rank"] for entry in board]
        assert ranks == [1, 2, 3]

    def test_same_score_preserves_input_order(self):
        items = _make_items([
            (1, "A", 70.0, 70.0),
            (2, "B", 70.0, 70.0),
        ])
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == board[1]["final_score"]


class TestLimit:
    """Verify TOP N limit."""

    def test_default_limit_100(self):
        items = _make_items([(i, f"商品{i}", 50.0, 50.0) for i in range(150)])
        board = RankingService().get_top_products(items)
        assert len(board) == 100

    def test_custom_limit(self):
        items = _make_items([(i, f"商品{i}", 50.0, 50.0) for i in range(20)])
        board = RankingService().get_top_products(items, limit=5)
        assert len(board) == 5

    def test_limit_larger_than_items(self):
        items = _make_items([(1, "A", 80.0, 80.0), (2, "B", 70.0, 70.0)])
        board = RankingService().get_top_products(items, limit=10)
        assert len(board) == 2

    def test_limit_one(self):
        items = _make_items([
            (1, "A", 90.0, 90.0),
            (2, "B", 50.0, 50.0),
        ])
        board = RankingService().get_top_products(items, limit=1)
        assert len(board) == 1
        assert board[0]["name"] == "A"


class TestLevel:
    """Verify level determination rules."""

    def test_hot_level(self):
        """final_score >= 90 → 爆款."""
        items = _make_items([(1, "爆款商品", 95.0, 95.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "爆款"
        assert board[0]["final_score"] == 95.0

    def test_potential_level(self):
        """70 <= final_score < 90 → 潜力."""
        items = _make_items([(1, "潜力商品", 80.0, 75.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "潜力"

    def test_normal_level(self):
        """50 <= final_score < 70 → 一般."""
        items = _make_items([(1, "一般商品", 60.0, 55.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "一般"

    def test_low_level(self):
        """final_score < 50 → 低潜."""
        items = _make_items([(1, "低潜商品", 30.0, 25.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "低潜"

    def test_boundary_90(self):
        """final_score == 90 → 爆款."""
        items = _make_items([(1, "边界", 90.0, 90.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "爆款"

    def test_boundary_70(self):
        """final_score == 70 → 潜力."""
        items = _make_items([(1, "边界", 70.0, 70.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "潜力"

    def test_boundary_50(self):
        """final_score == 50 → 一般."""
        items = _make_items([(1, "边界", 50.0, 50.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["level"] == "一般"


class TestEmptyData:
    """Verify empty/edge case handling."""

    def test_empty_list(self):
        board = RankingService().get_top_products([])
        assert board == []

    def test_none_scores_treated_as_zero(self):
        items = [{"product": _make_product(1, "测试"), "ai_score": None, "trend_score": None}]
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == 0.0
        assert board[0]["level"] == "低潜"

    def test_missing_scores_default_zero(self):
        items = [{"product": _make_product(1, "测试")}]
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == 0.0


class TestReturnFields:
    """Verify all required fields are present."""

    def test_all_fields_present(self):
        items = _make_items([(1, "蓝牙耳机", 85.0, 70.0)])
        board = RankingService().get_top_products(items)

        expected_keys = {
            "rank", "product_id", "name", "platform", "price",
            "ai_score", "trend_score", "final_score", "level",
        }
        assert set(board[0].keys()) == expected_keys

    def test_field_values_correct(self):
        product = _make_product(42, "保温杯", platform="小红书", price=49.9)
        items = [{"product": product, "ai_score": 80.0, "trend_score": 60.0}]
        board = RankingService().get_top_products(items)

        entry = board[0]
        assert entry["rank"] == 1
        assert entry["product_id"] == 42
        assert entry["name"] == "保温杯"
        assert entry["platform"] == "小红书"
        assert entry["price"] == 49.9
        assert entry["ai_score"] == 80.0
        assert entry["trend_score"] == 60.0
        assert entry["final_score"] == 80.0 * 0.6 + 60.0 * 0.4  # 72.0
        assert entry["level"] == "潜力"


class TestScoringFormula:
    """Verify the composite scoring formula."""

    def test_weights_applied(self):
        """ai_score * 0.6 + trend_score * 0.4."""
        items = _make_items([(1, "测试", 100.0, 0.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == 60.0  # 100*0.6 + 0*0.4

    def test_all_trend(self):
        items = _make_items([(1, "测试", 0.0, 100.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == 40.0  # 0*0.6 + 100*0.4

    def test_balanced(self):
        items = _make_items([(1, "测试", 50.0, 50.0)])
        board = RankingService().get_top_products(items)
        assert board[0]["final_score"] == 50.0  # 50*0.6 + 50*0.4
