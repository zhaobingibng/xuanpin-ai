"""Tests for data normalizer utilities."""

import pytest

from app.services.cleaner.normalizer import price_normalize, sales_normalize


class TestPriceNormalize:
    """5 groups of price normalization tests."""

    def test_currency_symbol_prefixixed(self):
        """¥ and ￥ prefixed prices."""
        assert price_normalize("¥39.9") == 39.9
        assert price_normalize("￥199.00") == 199.0
        assert price_normalize("¥0.01") == 0.01

    def test_yuan_suffix(self):
        """Prices with 元 suffix."""
        assert price_normalize("39元") == 39.0
        assert price_normalize("199.5元") == 199.5
        assert price_normalize("0元") == 0.0

    def test_plain_number_string(self):
        """Plain numeric strings."""
        assert price_normalize("39.90") == 39.9
        assert price_normalize("39") == 39.0
        assert price_normalize("0.5") == 0.5

    def test_numeric_types(self):
        """Direct float and int input."""
        assert price_normalize(39.9) == 39.9
        assert price_normalize(100) == 100.0
        assert price_normalize(0) == 0.0

    def test_invalid_input(self):
        """Invalid inputs should return None."""
        assert price_normalize("") is None
        assert price_normalize("abc") is None
        assert price_normalize(None) is None
        assert price_normalize("¥") is None


class TestSalesNormalize:
    """5 groups of sales normalization tests."""

    def test_wan_chinese(self):
        """Chinese 万 unit."""
        assert sales_normalize("1.2万") == 12000
        assert sales_normalize("3万") == 30000
        assert sales_normalize("0.5万") == 5000

    def test_w_latin(self):
        """Latin w/W unit (same as 万)."""
        assert sales_normalize("3.5w") == 35000
        assert sales_normalize("1W") == 10000
        assert sales_normalize("0.1w") == 1000

    def test_plain_number_string(self):
        """Plain numeric strings, including + suffix."""
        assert sales_normalize("12000") == 12000
        assert sales_normalize("12000+") == 12000
        assert sales_normalize("500") == 500

    def test_numeric_types(self):
        """Direct int input."""
        assert sales_normalize(12000) == 12000
        assert sales_normalize(0) == 0
        assert sales_normalize(999) == 999

    def test_invalid_input(self):
        """Invalid inputs should return None."""
        assert sales_normalize("") is None
        assert sales_normalize("abc") is None
        assert sales_normalize(None) is None
        assert sales_normalize("+") is None
