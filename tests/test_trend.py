"""Tests for trend calculation utilities."""

from app.services.analytics.trend import growth_rate, growth_to_score


class TestGrowthRate:
    """Test percentage growth rate calculation."""

    def test_increase(self):
        assert growth_rate(100.0, 150.0) == 50.0

    def test_decrease(self):
        assert growth_rate(100.0, 80.0) == -20.0

    def test_no_change(self):
        assert growth_rate(100.0, 100.0) == 0.0

    def test_double(self):
        assert growth_rate(50.0, 100.0) == 100.0

    def test_earliest_zero(self):
        assert growth_rate(0.0, 50.0) == 0.0

    def test_negative_growth(self):
        assert growth_rate(200.0, 50.0) == -75.0

    def test_small_values(self):
        assert growth_rate(10.0, 15.0) == 50.0


class TestGrowthToScore:
    """Test growth rate → 0-100 score conversion."""

    def test_zero_growth_is_50(self):
        assert growth_to_score(0.0) == 50.0

    def test_positive_100_is_100(self):
        assert growth_to_score(100.0) == 100.0

    def test_negative_100_is_0(self):
        assert growth_to_score(-100.0) == 0.0

    def test_positive_50(self):
        assert growth_to_score(50.0) == 75.0

    def test_negative_50(self):
        assert growth_to_score(-50.0) == 25.0

    def test_clamp_above_100(self):
        """Growth > 100% should cap at 100."""
        assert growth_to_score(200.0) == 100.0

    def test_clamp_below_0(self):
        """Growth < -100% should cap at 0."""
        assert growth_to_score(-200.0) == 0.0

    def test_small_positive(self):
        assert growth_to_score(10.0) == 55.0

    def test_small_negative(self):
        assert growth_to_score(-10.0) == 45.0
