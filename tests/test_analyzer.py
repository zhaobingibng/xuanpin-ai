"""Tests for TrendAnalyzer."""

from datetime import datetime, timedelta

from app.models.product_history import ProductHistory
from app.services.analytics.analyzer import TrendAnalyzer


def _make_history(
    product_id: int,
    records: list[tuple[float, int, int, float | None]],
) -> list[ProductHistory]:
    """Create ProductHistory snapshots from compact data.

    Args:
        product_id: FK reference.
        records: list of (price, sales_24h, viewers, ai_score) tuples.
    """
    base_time = datetime(2026, 7, 1, 9, 0, 0)
    result = []
    for i, (price, sales, viewers, ai) in enumerate(records):
        h = ProductHistory(
            id=i + 1,
            product_id=product_id,
            price=price,
            sales_24h=sales,
            viewers=viewers,
            ai_score=ai,
            record_time=base_time + timedelta(days=i),
        )
        result.append(h)
    return result


class TestCalculateSalesGrowth:
    """Test calculate_sales_growth()."""

    def test_double_sales(self):
        history = _make_history(1, [
            (100.0, 100, 500, 60.0),
            (100.0, 200, 500, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_sales_growth() == 100.0

    def test_half_sales(self):
        history = _make_history(1, [
            (100.0, 200, 500, 60.0),
            (100.0, 100, 500, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_sales_growth() == -50.0

    def test_no_change(self):
        history = _make_history(1, [
            (100.0, 100, 500, 60.0),
            (100.0, 100, 500, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_sales_growth() == 0.0

    def test_single_snapshot(self):
        history = _make_history(1, [(100.0, 50, 200, 60.0)])
        assert TrendAnalyzer(history).calculate_sales_growth() == 0.0

    def test_empty_history(self):
        assert TrendAnalyzer([]).calculate_sales_growth() == 0.0


class TestCalculateViewGrowth:
    """Test calculate_view_growth()."""

    def test_views_triple(self):
        history = _make_history(1, [
            (100.0, 50, 100, 60.0),
            (100.0, 50, 300, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_view_growth() == 200.0

    def test_views_drop(self):
        history = _make_history(1, [
            (100.0, 50, 400, 60.0),
            (100.0, 50, 100, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_view_growth() == -75.0

    def test_single_snapshot(self):
        history = _make_history(1, [(100.0, 50, 200, 60.0)])
        assert TrendAnalyzer(history).calculate_view_growth() == 0.0


class TestCalculatePriceChange:
    """Test calculate_price_change()."""

    def test_price_drop(self):
        history = _make_history(1, [
            (100.0, 50, 200, 60.0),
            (80.0, 50, 200, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_price_change() == -20.0

    def test_price_increase(self):
        history = _make_history(1, [
            (80.0, 50, 200, 60.0),
            (100.0, 50, 200, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_price_change() == 25.0

    def test_price_stable(self):
        history = _make_history(1, [
            (100.0, 50, 200, 60.0),
            (100.0, 50, 200, 60.0),
        ])
        assert TrendAnalyzer(history).calculate_price_change() == 0.0

    def test_single_snapshot(self):
        history = _make_history(1, [(100.0, 50, 200, 60.0)])
        assert TrendAnalyzer(history).calculate_price_change() == 0.0


class TestCalculateTrendScore:
    """Test calculate_trend_score() and level determination."""

    def test_explosive_growth(self):
        """Sales +200%, views +100%, price -20% → 爆发."""
        history = _make_history(1, [
            (100.0, 50, 100, 60.0),
            (80.0, 150, 200, 70.0),
        ])
        result = TrendAnalyzer(history).calculate_trend_score()

        assert result["level"] == "爆发"
        assert result["trend_score"] > 90
        assert result["sales_growth"] == 200.0
        assert result["view_growth"] == 100.0
        assert result["price_change"] == -20.0

    def test_rising(self):
        """Sales +60%, views +40%, price -10% → 上涨."""
        history = _make_history(1, [
            (100.0, 100, 200, 60.0),
            (90.0, 160, 280, 65.0),
        ])
        result = TrendAnalyzer(history).calculate_trend_score()

        assert result["level"] == "上涨"
        assert 70 <= result["trend_score"] <= 90

    def test_stable(self):
        """No growth → 稳定 (score = 50)."""
        history = _make_history(1, [
            (100.0, 100, 200, 60.0),
            (100.0, 100, 200, 60.0),
        ])
        result = TrendAnalyzer(history).calculate_trend_score()

        assert result["level"] == "稳定"
        assert result["trend_score"] == 50.0
        assert result["sales_growth"] == 0.0
        assert result["view_growth"] == 0.0
        assert result["price_change"] == 0.0

    def test_declining(self):
        """Sales -60%, views -40%, price +20% → 下降."""
        history = _make_history(1, [
            (100.0, 200, 300, 60.0),
            (120.0, 80, 180, 55.0),
        ])
        result = TrendAnalyzer(history).calculate_trend_score()

        assert result["level"] == "下降"
        assert result["trend_score"] < 50

    def test_result_keys(self):
        """Result dict should have all required keys."""
        history = _make_history(1, [
            (100.0, 50, 100, 60.0),
            (100.0, 50, 100, 60.0),
        ])
        result = TrendAnalyzer(history).calculate_trend_score()

        expected_keys = {"trend_score", "sales_growth", "view_growth", "price_change", "level"}
        assert set(result.keys()) == expected_keys

    def test_empty_history(self):
        """Empty history should return stable with zeros."""
        result = TrendAnalyzer([]).calculate_trend_score()

        assert result["trend_score"] == 50.0
        assert result["level"] == "稳定"
        assert result["sales_growth"] == 0.0
        assert result["view_growth"] == 0.0
        assert result["price_change"] == 0.0

    def test_single_snapshot(self):
        """Single snapshot should return stable with zero growth."""
        history = _make_history(1, [(100.0, 50, 100, 60.0)])
        result = TrendAnalyzer(history).calculate_trend_score()

        assert result["trend_score"] == 50.0
        assert result["level"] == "稳定"

    def test_price_advantage_scoring(self):
        """Price drop should boost trend_score via price advantage."""
        # Same sales/views, only price drops
        history_flat = _make_history(1, [
            (100.0, 100, 200, 60.0),
            (100.0, 100, 200, 60.0),
        ])
        history_drop = _make_history(1, [
            (100.0, 100, 200, 60.0),
            (80.0, 100, 200, 60.0),
        ])

        score_flat = TrendAnalyzer(history_flat).calculate_trend_score()["trend_score"]
        score_drop = TrendAnalyzer(history_drop).calculate_trend_score()["trend_score"]

        assert score_drop > score_flat

    def test_unsorted_history_sorted_internally(self):
        """Analyzer should sort by record_time regardless of input order."""
        base = datetime(2026, 7, 1, 9, 0, 0)
        h1 = ProductHistory(id=1, product_id=1, price=100.0, sales_24h=50, viewers=100, record_time=base)
        h2 = ProductHistory(id=2, product_id=1, price=80.0, sales_24h=150, viewers=200, record_time=base + timedelta(days=2))
        h3 = ProductHistory(id=3, product_id=1, price=90.0, sales_24h=100, viewers=150, record_time=base + timedelta(days=1))

        # Pass in wrong order — should still use earliest/latest correctly
        analyzer = TrendAnalyzer([h2, h1, h3])
        assert analyzer.calculate_sales_growth() == 200.0  # 50→150
        assert analyzer.calculate_price_change() == -20.0   # 100→80

    def test_level_boundaries(self):
        """Test exact level boundary values."""
        assert TrendAnalyzer._determine_level(91.0) == "爆发"
        assert TrendAnalyzer._determine_level(90.0) == "上涨"
        assert TrendAnalyzer._determine_level(70.0) == "上涨"
        assert TrendAnalyzer._determine_level(69.9) == "稳定"
        assert TrendAnalyzer._determine_level(50.0) == "稳定"
        assert TrendAnalyzer._determine_level(49.9) == "下降"
        assert TrendAnalyzer._determine_level(0.0) == "下降"
