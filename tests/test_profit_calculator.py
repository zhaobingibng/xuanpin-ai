"""Tests for Phase 14 Task 4: ProfitCalculator service."""

import pytest

from app.services.supply_chain.profit_calculator import (
    ProfitCalculator,
    ProfitResult,
    CATEGORY_FEE_RATES,
    CATEGORY_SHIPPING_RATES,
)


class TestProfitCalculator:
    """ProfitCalculator 单元测试。"""

    def setup_method(self):
        self.calc = ProfitCalculator()

    # ── 基本计算 ──────────────────────────────────────────────

    def test_basic_profit_calculation(self):
        """基本利润计算。"""
        result = self.calc.calculate(sell_price=100.0, cost_price=30.0)
        # 佣金: 100 * 0.05 = 5
        # 运费: 5
        # 利润: 100 - 30 - 5 - 5 = 60
        assert result.profit_amount == 60.0
        assert result.profit_margin == 60.0

    def test_zero_sell_price(self):
        """售价为 0 时利润为负（仍有运费和成本）。"""
        result = self.calc.calculate(sell_price=0.0, cost_price=30.0)
        # 利润 = 0 - 30 - 0(佣金) - 5(运费) = -35
        assert result.profit_amount == -35.0
        assert result.profit_margin == 0.0  # 售价为 0 时利润率返回 0

    def test_negative_profit(self):
        """亏损场景。"""
        result = self.calc.calculate(sell_price=10.0, cost_price=50.0)
        assert result.profit_amount < 0
        assert result.profit_margin < 0

    def test_high_margin_product(self):
        """高利润商品。"""
        result = self.calc.calculate(sell_price=200.0, cost_price=20.0)
        assert result.profit_margin > 50

    # ── 品类佣金率 ─────────────────────────────────────────────

    def test_category_fee_rate_bluetooth(self):
        """蓝牙耳机品类佣金率。"""
        result = self.calc.calculate(
            sell_price=100.0, cost_price=30.0, category="蓝牙耳机"
        )
        assert result.fee_rate == CATEGORY_FEE_RATES["蓝牙耳机"]

    def test_category_fee_rate_default(self):
        """未知品类使用默认佣金率。"""
        result = self.calc.calculate(
            sell_price=100.0, cost_price=30.0, category="工业零件"
        )
        assert result.fee_rate == CATEGORY_FEE_RATES["default"]

    def test_custom_fee_rate(self):
        """自定义佣金率覆盖品类默认值。"""
        result = self.calc.calculate(
            sell_price=100.0, cost_price=30.0,
            category="蓝牙耳机", fee_rate=0.10
        )
        assert result.fee_rate == 0.10

    # ── 运费模板 ──────────────────────────────────────────────

    def test_category_shipping_phone_case(self):
        """手机壳运费。"""
        result = self.calc.calculate(
            sell_price=30.0, cost_price=5.0, category="手机壳"
        )
        assert result.shipping_cost == CATEGORY_SHIPPING_RATES["手机壳"]

    def test_category_shipping_storage(self):
        """收纳品类运费。"""
        result = self.calc.calculate(
            sell_price=50.0, cost_price=10.0, category="收纳神器"
        )
        assert result.shipping_cost == CATEGORY_SHIPPING_RATES["收纳"]

    def test_custom_shipping(self):
        """自定义运费覆盖品类默认值。"""
        result = self.calc.calculate(
            sell_price=100.0, cost_price=30.0,
            category="蓝牙耳机", shipping_cost=10.0
        )
        assert result.shipping_cost == 10.0

    # ── ROI 计算 ──────────────────────────────────────────────

    def test_roi_positive(self):
        """ROI 应为正数（盈利场景）。"""
        result = self.calc.calculate(sell_price=100.0, cost_price=20.0)
        assert result.roi > 0

    def test_roi_negative(self):
        """ROI 应为负数（亏损场景）。"""
        result = self.calc.calculate(sell_price=10.0, cost_price=50.0)
        assert result.roi < 0

    def test_roi_zero_cost(self):
        """成本为 0 时 ROI 为 0。"""
        result = self.calc.calculate(sell_price=100.0, cost_price=0.0)
        assert result.roi == 0.0

    # ── 批量计算 ──────────────────────────────────────────────

    def test_batch_calculate(self):
        """批量计算。"""
        items = [
            {"sell_price": 100.0, "cost_price": 30.0, "category": "蓝牙耳机"},
            {"sell_price": 50.0, "cost_price": 10.0, "category": "手机壳"},
            {"sell_price": 200.0, "cost_price": 80.0, "category": "收纳"},
        ]
        results = self.calc.batch_calculate(items)
        assert len(results) == 3
        assert all(isinstance(r, ProfitResult) for r in results)

    def test_batch_calculate_empty(self):
        """空列表批量计算。"""
        results = self.calc.batch_calculate([])
        assert len(results) == 0

    # ── ProfitResult ──────────────────────────────────────────

    def test_profit_result_to_dict(self):
        """ProfitResult.to_dict() 应返回正确结构。"""
        result = ProfitResult(
            sell_price=100.0,
            cost_price=30.0,
            fee_rate=0.05,
            fee_amount=5.0,
            shipping_cost=5.0,
            profit_amount=60.0,
            profit_margin=60.0,
            roi=200.0,
        )
        d = result.to_dict()
        assert d["sell_price"] == 100.0
        assert d["profit_amount"] == 60.0
        assert d["profit_margin"] == 60.0
        assert d["roi"] == 200.0

    # ── 边界条件 ──────────────────────────────────────────────

    def test_very_low_price(self):
        """极低价商品。"""
        result = self.calc.calculate(sell_price=1.0, cost_price=0.5)
        assert result.profit_amount < 0  # 运费 5 元 > 售价

    def test_very_high_price(self):
        """高价商品。"""
        result = self.calc.calculate(sell_price=10000.0, cost_price=1000.0)
        assert result.profit_amount > 0
        assert result.profit_margin > 50

    def test_empty_category(self):
        """空品类使用默认值。"""
        result = self.calc.calculate(sell_price=100.0, cost_price=30.0, category="")
        assert result.fee_rate == self.calc._default_fee_rate
        assert result.shipping_cost == self.calc._default_shipping
