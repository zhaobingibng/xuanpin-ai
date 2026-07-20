"""Tests for ProductScorer — comprehensive scoring engine."""

from datetime import datetime, timedelta

import pytest

from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.scoring.product_scorer import ProductScorer


# ── Helpers ──────────────────────────────────────────────────


def _product(
    sales_24h: int = 0,
    viewers: int = 0,
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
    """Build ProductHistory list from parallel sales/viewers arrays."""
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


# ── TestSalesScore ───────────────────────────────────────────


class TestSalesScore:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_10000_plus(self):
        p = _product(sales_24h=12000)
        result = self.scorer.calculate_score(p)
        # sales: 30 + trend(5) + viewers(3) + price(15) + profit(10) = 63
        assert any("24小时销量12000" in r for r in result["reasons"])

    def test_5000_to_10000(self):
        p = _product(sales_24h=7000)
        result = self.scorer.calculate_score(p)
        assert any("7000" in r for r in result["reasons"])

    def test_1000_to_5000(self):
        p = _product(sales_24h=3000)
        result = self.scorer.calculate_score(p)
        assert any("3000" in r for r in result["reasons"])

    def test_100_to_1000(self):
        p = _product(sales_24h=500)
        result = self.scorer.calculate_score(p)
        assert any("500" in r for r in result["reasons"])

    def test_below_100(self):
        p = _product(sales_24h=50)
        result = self.scorer.calculate_score(p)
        assert any("50" in r for r in result["reasons"])

    def test_exact_10000(self):
        """Boundary: sales_24h == 10000 → 30 points."""
        p = _product(sales_24h=10000, price=100.0, viewers=50000)
        result = self.scorer.calculate_score(p)
        # sales: 30, viewers: 15, price: 15, profit: 10
        # trend: no history → 5
        assert result["score"] == 75


# ── TestTrendScore ───────────────────────────────────────────


class TestTrendScore:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_growth_above_100_percent(self):
        history = _history_list(sales=[100, 300])  # 200% growth
        p = _product(sales_24h=300)
        result = self.scorer.calculate_score(p, history)
        assert any("200%" in r for r in result["reasons"])

    def test_growth_50_to_100_percent(self):
        history = _history_list(sales=[100, 180])  # 80% growth
        p = _product(sales_24h=180)
        result = self.scorer.calculate_score(p, history)
        assert any("80%" in r for r in result["reasons"])

    def test_growth_10_to_50_percent(self):
        history = _history_list(sales=[100, 130])  # 30% growth
        p = _product(sales_24h=130)
        result = self.scorer.calculate_score(p, history)
        assert any("30%" in r for r in result["reasons"])

    def test_growth_0_to_10_percent(self):
        history = _history_list(sales=[100, 105])  # 5% growth
        p = _product(sales_24h=105)
        result = self.scorer.calculate_score(p, history)
        assert any("5%" in r for r in result["reasons"])

    def test_growth_negative(self):
        history = _history_list(sales=[100, 50])  # -50% growth
        p = _product(sales_24h=50)
        result = self.scorer.calculate_score(p, history)
        assert any("-50%" in r for r in result["reasons"])

    def test_no_history(self):
        """No history → trend score = 5 (default)."""
        p = _product(sales_24h=100)
        result = self.scorer.calculate_score(p, history=None)
        assert any("暂无趋势数据" in r for r in result["reasons"])

    def test_single_snapshot(self):
        """Only 1 history record → treated as no trend."""
        history = _history_list(sales=[100])
        p = _product(sales_24h=100)
        result = self.scorer.calculate_score(p, history)
        assert any("暂无趋势数据" in r for r in result["reasons"])


# ── TestViewersScore ─────────────────────────────────────────


class TestViewersScore:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_50000_plus(self):
        p = _product(viewers=60000)
        result = self.scorer.calculate_score(p)
        assert any("60000" in r for r in result["reasons"])

    def test_10000_to_50000(self):
        p = _product(viewers=30000)
        result = self.scorer.calculate_score(p)
        assert any("30000" in r for r in result["reasons"])

    def test_1000_to_10000(self):
        p = _product(viewers=5000)
        result = self.scorer.calculate_score(p)
        assert any("5000" in r for r in result["reasons"])

    def test_below_1000(self):
        p = _product(viewers=500)
        result = self.scorer.calculate_score(p)
        assert any("500" in r for r in result["reasons"])


# ── TestPriceScore ───────────────────────────────────────────


class TestPriceScore:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_20_to_200(self):
        p = _product(price=99.0)
        result = self.scorer.calculate_score(p)
        assert any("99.0" in r for r in result["reasons"])

    def test_10_to_20(self):
        p = _product(price=15.0)
        result = self.scorer.calculate_score(p)
        assert any("15.0" in r for r in result["reasons"])

    def test_200_to_500(self):
        p = _product(price=350.0)
        result = self.scorer.calculate_score(p)
        assert any("350.0" in r for r in result["reasons"])

    def test_below_10(self):
        p = _product(price=5.0)
        result = self.scorer.calculate_score(p)
        assert any("5.0" in r for r in result["reasons"])

    def test_above_500(self):
        p = _product(price=800.0)
        result = self.scorer.calculate_score(p)
        assert any("800.0" in r for r in result["reasons"])

    def test_boundary_20(self):
        p = _product(price=20.0)
        result = self.scorer.calculate_score(p)
        assert any("20.0" in r for r in result["reasons"])

    def test_boundary_200(self):
        p = _product(price=200.0)
        result = self.scorer.calculate_score(p)
        assert any("200.0" in r for r in result["reasons"])


# ── TestLevel ────────────────────────────────────────────────


class TestLevel:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_hot_level(self):
        """score >= 90 → 爆款."""
        # sales(30) + trend(5) + viewers(15) + price(15) + profit(10) = 75
        # Need history for trend boost: growth >100% → 25 → total = 95
        history = _history_list(sales=[100, 500])  # 400% growth
        p = _product(sales_24h=12000, viewers=60000, price=99.0)
        result = self.scorer.calculate_score(p, history)
        assert result["level"] == "爆款"
        assert result["score"] >= 90

    def test_potential_level(self):
        """70 <= score < 90 → 潜力."""
        # sales(20) + trend(5) + viewers(7) + price(15) + profit(10) = 57
        # Need a bit more: sales=1000→20, viewers=1000→7
        p = _product(sales_24h=2000, viewers=5000, price=50.0)
        result = self.scorer.calculate_score(p)
        # 20 + 5 + 7 + 15 + 10 = 57 — that's "一般"
        # Let's use higher values
        p2 = _product(sales_24h=6000, viewers=15000, price=100.0)
        result2 = self.scorer.calculate_score(p2)
        # 25 + 5 + 10 + 15 + 10 = 65 — still "一般"
        # Need history for trend boost
        history = _history_list(sales=[100, 160])  # 60% growth → 20
        p3 = _product(sales_24h=6000, viewers=15000, price=100.0)
        result3 = self.scorer.calculate_score(p3, history)
        # 25 + 20 + 10 + 15 + 10 = 80
        assert result3["score"] == 80
        assert result3["level"] == "潜力"

    def test_normal_level(self):
        """50 <= score < 70 → 一般."""
        p = _product(sales_24h=500, viewers=2000, price=50.0)
        result = self.scorer.calculate_score(p)
        # 10 + 5 + 7 + 15 + 10 = 47 — too low
        p2 = _product(sales_24h=1500, viewers=2000, price=50.0)
        result2 = self.scorer.calculate_score(p2)
        # 20 + 5 + 7 + 15 + 10 = 57
        assert 50 <= result2["score"] < 70
        assert result2["level"] == "一般"

    def test_low_level(self):
        """score < 50 → 低潜."""
        p = _product(sales_24h=10, viewers=100, price=5.0)
        result = self.scorer.calculate_score(p)
        # 5 + 5 + 3 + 5 + 10 = 28
        assert result["score"] < 50
        assert result["level"] == "低潜"

    def test_boundary_90(self):
        """score == 90 → 爆款."""
        assert ProductScorer._determine_level(90) == "爆款"

    def test_boundary_70(self):
        """score == 70 → 潜力."""
        assert ProductScorer._determine_level(70) == "潜力"

    def test_boundary_50(self):
        """score == 50 → 一般."""
        assert ProductScorer._determine_level(50) == "一般"

    def test_boundary_49(self):
        """score == 49 → 低潜."""
        assert ProductScorer._determine_level(49) == "低潜"


# ── TestReasons ──────────────────────────────────────────────


class TestReasons:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_reasons_is_list(self):
        p = _product(sales_24h=100, viewers=500, price=50.0)
        result = self.scorer.calculate_score(p)
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) >= 4

    def test_reasons_contain_sales(self):
        p = _product(sales_24h=12000)
        result = self.scorer.calculate_score(p)
        assert any("24小时销量12000" in r for r in result["reasons"])

    def test_reasons_contain_growth(self):
        history = _history_list(sales=[100, 185])  # 85% growth
        p = _product(sales_24h=185)
        result = self.scorer.calculate_score(p, history)
        assert any("85%" in r for r in result["reasons"])

    def test_reasons_contain_viewers(self):
        p = _product(viewers=52000)
        result = self.scorer.calculate_score(p)
        assert any("52000" in r for r in result["reasons"])

    def test_reasons_contain_price(self):
        p = _product(price=199.0)
        result = self.scorer.calculate_score(p)
        assert any("199.0" in r for r in result["reasons"])


# ── TestReturnFormat ─────────────────────────────────────────


class TestReturnFormat:

    def setup_method(self):
        self.scorer = ProductScorer()

    def test_return_keys(self):
        p = _product()
        result = self.scorer.calculate_score(p)
        assert "score" in result
        assert "level" in result
        assert "reasons" in result

    def test_score_is_int(self):
        p = _product()
        result = self.scorer.calculate_score(p)
        assert isinstance(result["score"], int)

    def test_level_is_string(self):
        p = _product()
        result = self.scorer.calculate_score(p)
        assert isinstance(result["level"], str)

    def test_score_range(self):
        """Score should be between 0 and 100."""
        p_low = _product(sales_24h=0, viewers=0, price=0.0)
        r_low = self.scorer.calculate_score(p_low)
        assert 0 <= r_low["score"] <= 100

        history = _history_list(sales=[1, 10000])  # massive growth
        p_high = _product(sales_24h=50000, viewers=100000, price=99.0)
        r_high = self.scorer.calculate_score(p_high, history)
        assert 0 <= r_high["score"] <= 100
