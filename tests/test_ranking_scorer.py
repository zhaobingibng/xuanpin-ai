"""Tests for RankingService with ProductScorer integration."""

from datetime import datetime, timedelta

import pytest

from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.ranking.ranking import RankingService


# ── Helpers ──────────────────────────────────────────────────


def _product(
    pid: int, name: str,
    sales_24h: int = 0, viewers: int = 0,
    price: float = 99.0, platform: str = "xiaohongshu",
) -> Product:
    return Product(
        id=pid, name=name, platform=platform, shop="测试店铺",
        price=price, sales_24h=sales_24h, viewers=viewers,
    )


def _history_list(
    product_id: int,
    sales: list[int],
    price: float = 99.0,
) -> list[ProductHistory]:
    now = datetime.utcnow()
    return [
        ProductHistory(
            product_id=product_id, price=price,
            sales_24h=s, viewers=0,
            record_time=now - timedelta(minutes=(len(sales) - i) * 60),
        )
        for i, s in enumerate(sales)
    ]


def _scorer_items(data: list[tuple]) -> list[dict]:
    """Build items for scorer mode.

    Each tuple: (product, history_or_None).
    """
    return [{"product": p, "history": h} for p, h in data]


# ── TestRankingScorerOrder ───────────────────────────────────


class TestRankingScorerOrder:

    def test_highest_score_first(self):
        svc = RankingService()
        p_low = _product(1, "低分商品", sales_24h=10, viewers=100, price=5.0)
        p_high = _product(2, "高分商品", sales_24h=12000, viewers=60000, price=99.0)
        h_high = _history_list(2, sales=[100, 500])  # 400% growth

        items = _scorer_items([
            (p_low, None),
            (p_high, h_high),
        ])
        board = svc.get_top_products(items)

        assert board[0]["name"] == "高分商品"
        assert board[0]["rank"] == 1
        assert board[1]["name"] == "低分商品"
        assert board[1]["rank"] == 2

    def test_rank_assignment(self):
        svc = RankingService()
        items = _scorer_items([
            (_product(1, "A", sales_24h=12000, viewers=60000, price=99.0), _history_list(1, [100, 500])),
            (_product(2, "B", sales_24h=5000, viewers=20000, price=99.0), None),
            (_product(3, "C", sales_24h=100, viewers=500, price=50.0), None),
        ])
        board = svc.get_top_products(items)
        ranks = [e["rank"] for e in board]
        assert ranks == [1, 2, 3]

    def test_sorted_by_score_desc(self):
        svc = RankingService()
        items = _scorer_items([
            (_product(1, "A", sales_24h=500, price=99.0), None),
            (_product(2, "B", sales_24h=6000, price=99.0), None),
            (_product(3, "C", sales_24h=100, price=99.0), None),
        ])
        board = svc.get_top_products(items)
        scores = [e["score"] for e in board]
        assert scores == sorted(scores, reverse=True)


# ── TestRankingScorerLimit ───────────────────────────────────


class TestRankingScorerLimit:

    def test_default_limit_100(self):
        svc = RankingService()
        items = _scorer_items([
            (_product(i, f"商品{i}", sales_24h=100, price=99.0), None)
            for i in range(150)
        ])
        board = svc.get_top_products(items)
        assert len(board) == 100

    def test_custom_limit(self):
        svc = RankingService()
        items = _scorer_items([
            (_product(i, f"商品{i}", sales_24h=100, price=99.0), None)
            for i in range(20)
        ])
        board = svc.get_top_products(items, limit=5)
        assert len(board) == 5

    def test_empty_list(self):
        svc = RankingService()
        board = svc.get_top_products([])
        assert board == []


# ── TestRankingScorerLevel ───────────────────────────────────


class TestRankingScorerLevel:

    def test_hot_level(self):
        svc = RankingService()
        history = _history_list(1, sales=[100, 500])  # 400% → 25 trend
        p = _product(1, "爆款", sales_24h=12000, viewers=60000, price=99.0)
        # 30 + 25 + 15 + 15 + 10 = 95
        items = _scorer_items([(p, history)])
        board = svc.get_top_products(items)
        assert board[0]["level"] == "爆款"
        assert board[0]["score"] >= 90

    def test_potential_level(self):
        svc = RankingService()
        history = _history_list(1, sales=[100, 160])  # 60% → 20 trend
        p = _product(1, "潜力", sales_24h=6000, viewers=15000, price=100.0)
        # 25 + 20 + 10 + 15 + 10 = 80
        items = _scorer_items([(p, history)])
        board = svc.get_top_products(items)
        assert board[0]["level"] == "潜力"
        assert 70 <= board[0]["score"] < 90

    def test_normal_level(self):
        svc = RankingService()
        p = _product(1, "一般", sales_24h=1500, viewers=2000, price=50.0)
        # 20 + 5 + 7 + 15 + 10 = 57
        items = _scorer_items([(p, None)])
        board = svc.get_top_products(items)
        assert board[0]["level"] == "一般"
        assert 50 <= board[0]["score"] < 70

    def test_low_level(self):
        svc = RankingService()
        p = _product(1, "低潜", sales_24h=10, viewers=100, price=5.0)
        # 5 + 5 + 3 + 5 + 10 = 28
        items = _scorer_items([(p, None)])
        board = svc.get_top_products(items)
        assert board[0]["level"] == "低潜"
        assert board[0]["score"] < 50


# ── TestRankingScorerFields ──────────────────────────────────


class TestRankingScorerFields:

    def test_all_fields_present(self):
        svc = RankingService()
        p = _product(42, "蓝牙耳机", sales_24h=500, price=99.0, platform="xiaohongshu")
        items = _scorer_items([(p, None)])
        board = svc.get_top_products(items)

        entry = board[0]
        assert "rank" in entry
        assert "product_id" in entry
        assert "name" in entry
        assert "platform" in entry
        assert "price" in entry
        assert "score" in entry
        assert "level" in entry
        assert "reasons" in entry

    def test_field_values_correct(self):
        svc = RankingService()
        p = _product(42, "蓝牙耳机", sales_24h=500, price=99.0, platform="xiaohongshu")
        items = _scorer_items([(p, None)])
        board = svc.get_top_products(items)

        entry = board[0]
        assert entry["rank"] == 1
        assert entry["product_id"] == 42
        assert entry["name"] == "蓝牙耳机"
        assert entry["platform"] == "xiaohongshu"
        assert entry["price"] == 99.0
        assert isinstance(entry["score"], int)
        assert isinstance(entry["reasons"], list)

    def test_reasons_populated(self):
        svc = RankingService()
        history = _history_list(1, sales=[100, 185])  # 85% growth
        p = _product(1, "测试商品", sales_24h=5000, viewers=30000, price=99.0)
        items = _scorer_items([(p, history)])
        board = svc.get_top_products(items)

        reasons = board[0]["reasons"]
        assert any("24小时销量5000" in r for r in reasons)
        assert any("85%" in r for r in reasons)
        assert any("30000" in r for r in reasons)
