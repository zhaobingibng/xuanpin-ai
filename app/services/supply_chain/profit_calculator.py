"""ProfitCalculator — calculate profit margin between retail and wholesale prices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProfitResult:
    """利润计算结果。"""

    sell_price: float       # 售价
    cost_price: float       # 成本价
    fee_rate: float         # 平台佣金率
    fee_amount: float       # 佣金金额
    shipping_cost: float    # 运费
    profit_amount: float    # 利润额
    profit_margin: float    # 利润率 (%)
    roi: float              # 投资回报率 (%)

    def to_dict(self) -> dict[str, Any]:
        """转为字典。"""
        return {
            "sell_price": self.sell_price,
            "cost_price": self.cost_price,
            "fee_rate": self.fee_rate,
            "fee_amount": round(self.fee_amount, 2),
            "shipping_cost": self.shipping_cost,
            "profit_amount": round(self.profit_amount, 2),
            "profit_margin": round(self.profit_margin, 2),
            "roi": round(self.roi, 2),
        }


# 品类佣金率配置 (淘宝)
CATEGORY_FEE_RATES: dict[str, float] = {
    "蓝牙耳机": 0.05,
    "手机壳": 0.05,
    "收纳": 0.05,
    "宠物": 0.05,
    "美妆": 0.05,
    "女装": 0.05,
    "家居": 0.05,
    "default": 0.05,
}

# 品类运费模板 (元)
CATEGORY_SHIPPING_RATES: dict[str, float] = {
    "蓝牙耳机": 5.0,
    "手机壳": 3.0,
    "收纳": 8.0,
    "宠物": 6.0,
    "美妆": 4.0,
    "女装": 6.0,
    "家居": 8.0,
    "default": 5.0,
}


class ProfitCalculator:
    """利润计算器。

    根据售价、成本价、品类计算利润空间。

    Usage::

        calc = ProfitCalculator()
        result = calc.calculate(sell_price=59.9, cost_price=15.8, category="蓝牙耳机")
        print(f"利润: {result.profit_amount:.2f}元, 利润率: {result.profit_margin:.1f}%")
    """

    def __init__(
        self,
        default_fee_rate: float = 0.05,
        default_shipping: float = 5.0,
    ) -> None:
        self._default_fee_rate = default_fee_rate
        self._default_shipping = default_shipping

    def calculate(
        self,
        sell_price: float,
        cost_price: float,
        category: str = "",
        fee_rate: float | None = None,
        shipping_cost: float | None = None,
    ) -> ProfitResult:
        """计算利润空间。

        Args:
            sell_price: 售价 (淘宝零售价)。
            cost_price: 成本价 (1688批发价)。
            category: 商品品类 (用于匹配佣金率和运费模板)。
            fee_rate: 自定义佣金率，None 使用品类默认值。
            shipping_cost: 自定义运费，None 使用品类默认值。

        Returns:
            ProfitResult 包含完整利润分析。
        """
        # 确定佣金率
        if fee_rate is None:
            fee_rate = self._get_fee_rate(category)

        # 确定运费
        if shipping_cost is None:
            shipping_cost = self._get_shipping_cost(category)

        # 计算各项
        fee_amount = sell_price * fee_rate
        profit_amount = sell_price - cost_price - fee_amount - shipping_cost
        profit_margin = (profit_amount / sell_price * 100) if sell_price > 0 else 0.0
        roi = (profit_amount / cost_price * 100) if cost_price > 0 else 0.0

        return ProfitResult(
            sell_price=sell_price,
            cost_price=cost_price,
            fee_rate=fee_rate,
            fee_amount=fee_amount,
            shipping_cost=shipping_cost,
            profit_amount=profit_amount,
            profit_margin=profit_margin,
            roi=roi,
        )

    def batch_calculate(
        self,
        items: list[dict[str, float]],
    ) -> list[ProfitResult]:
        """批量计算利润。

        Args:
            items: [{"sell_price": float, "cost_price": float, "category": str}, ...]

        Returns:
            每项的利润计算结果列表。
        """
        results: list[ProfitResult] = []
        for item in items:
            result = self.calculate(
                sell_price=item.get("sell_price", 0.0),
                cost_price=item.get("cost_price", 0.0),
                category=item.get("category", ""),
            )
            results.append(result)
        return results

    def _get_fee_rate(self, category: str) -> float:
        """获取品类佣金率。"""
        if not category:
            return self._default_fee_rate
        for key, rate in CATEGORY_FEE_RATES.items():
            if key in category:
                return rate
        return self._default_fee_rate

    def _get_shipping_cost(self, category: str) -> float:
        """获取品类运费。"""
        if not category:
            return self._default_shipping
        for key, cost in CATEGORY_SHIPPING_RATES.items():
            if key in category:
                return cost
        return self._default_shipping
