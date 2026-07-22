"""Product Scoring Service — 新品价值评分服务.

评分维度（总分100）：
- shop_score: 店铺权重 (0-30)
- price_score: 价格评分 (0-20)
- category_score: 类目潜力 (0-15)
- newness_score: 新品程度 (0-25)
- completeness_score: 数据完整度 (0-10)

推荐等级：
- 90-100: ★★★★★ 强烈关注
- 75-89: ★★★★ 推荐关注
- 60-74: ★★★ 观察
- <60: 暂不推荐
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.models.product import Product
from app.models.product_score import ProductScore


# ── 推荐等级常量 ─────────────────────────────────────────────

RECOMMEND_STRONG = "★★★★★ 强烈关注"
RECOMMEND_WATCH = "★★★★ 推荐关注"
RECOMMEND_OBSERVE = "★★★ 观察"
RECOMMEND_SKIP = "暂不推荐"


# ── 头部店铺关键词（用于店铺权重评分）────────────────────────

TOP_SHOP_KEYWORDS = [
    "旗舰店", "官方旗舰店", "自营", "专卖店",
    "旗舰", "官方", "品牌",
]

# ── 高潜力类目 ─────────────────────────────────────────────

HIGH_POTENTIAL_CATEGORIES = [
    "美妆", "护肤", "彩妆", "零食", "母婴",
    "健康", "运动", "户外", "家居", "收纳",
]

MEDIUM_POTENTIAL_CATEGORIES = [
    "服饰", "鞋包", "数码", "家电", "文具",
]


class ProductScoringService:
    """新品价值评分服务。

    评分规则（第一版）：
    总分100分，5个维度：
    1. 店铺权重 (0-30): 根据店铺名称特征判断
    2. 新品程度 (0-25): 根据首次发现时间判断
    3. 价格区间 (0-20): 根据价格判断
    4. 类目潜力 (0-15): 根据类目判断
    5. 数据完整度 (0-10): 根据数据字段完整度判断

    Usage::

        service = ProductScoringService()
        score = service.calculate_score(product)
        # score = {
        #     "shop_score": 25.0,
        #     "price_score": 15.0,
        #     "category_score": 10.0,
        #     "newness_score": 20.0,
        #     "completeness_score": 8.0,
        #     "total_score": 78.0,
        #     "recommend_level": "★★★★ 推荐关注",
        # }
    """

    # ── 评分维度最大值 ──────────────────────────────────────

    MAX_SHOP_SCORE = 30
    MAX_NEWNESS_SCORE = 25
    MAX_PRICE_SCORE = 20
    MAX_CATEGORY_SCORE = 15
    MAX_COMPLETENESS_SCORE = 10

    # ── Public API ──────────────────────────────────────────

    def calculate_score(self, product: Product) -> dict[str, Any]:
        """计算商品价值评分。

        Args:
            product: Product ORM 实例。

        Returns:
            Dict with scoring details:
            {
                "shop_score": float,
                "price_score": float,
                "category_score": float,
                "newness_score": float,
                "completeness_score": float,
                "total_score": float,
                "recommend_level": str,
            }
        """
        shop_score = self._score_shop(product.shop)
        price_score = self._score_price(product.price)
        category_score = self._score_category(product.category)
        newness_score = self._score_newness(product.first_seen_time)
        completeness_score = self._score_completeness(product)

        total_score = (
            shop_score + price_score + category_score +
            newness_score + completeness_score
        )

        recommend_level = self._get_recommend_level(total_score)

        return {
            "shop_score": shop_score,
            "price_score": price_score,
            "category_score": category_score,
            "newness_score": newness_score,
            "completeness_score": completeness_score,
            "total_score": total_score,
            "recommend_level": recommend_level,
        }

    def create_score_record(self, product: Product) -> ProductScore:
        """创建评分记录。

        Args:
            product: Product ORM 实例。

        Returns:
            ProductScore ORM 实例。
        """
        score_data = self.calculate_score(product)

        return ProductScore(
            product_id=product.id,
            shop_score=score_data["shop_score"],
            price_score=score_data["price_score"],
            category_score=score_data["category_score"],
            newness_score=score_data["newness_score"],
            completeness_score=score_data["completeness_score"],
            total_score=score_data["total_score"],
            recommend_level=score_data["recommend_level"],
        )

    # ── 内部评分方法 ────────────────────────────────────────

    def _score_shop(self, shop_name: str | None) -> float:
        """店铺权重评分 (0-30)。

        规则：
        - 包含"旗舰店"/"官方"/"自营"等关键词：25-30分
        - 包含"专卖"/"品牌"等：15-24分
        - 其他：5-14分
        """
        if not shop_name:
            return 5.0

        shop_lower = shop_name.lower()

        # 头部店铺特征
        for keyword in TOP_SHOP_KEYWORDS:
            if keyword in shop_lower:
                # 官方旗舰店最高分
                if "官方" in shop_lower and "旗舰" in shop_lower:
                    return 30.0
                if "自营" in shop_lower:
                    return 28.0
                if "旗舰" in shop_lower:
                    return 25.0
                return 20.0

        # 普通店铺
        return 10.0

    def _score_price(self, price: float | None) -> float:
        """价格区间评分 (0-20)。

        规则（适合跟卖的价格区间）：
        - 10-100元：高利润空间，20分
        - 100-300元：中等利润，15分
        - 300-500元：较高客单，12分
        - <10元或>500元：风险较高，5-8分
        """
        if price is None or price <= 0:
            return 5.0

        if 10 <= price <= 100:
            return 20.0
        elif 100 < price <= 300:
            return 15.0
        elif 300 < price <= 500:
            return 12.0
        elif price < 10:
            return 8.0
        else:  # > 500
            return 5.0

    def _score_category(self, category: str | None) -> float:
        """类目潜力评分 (0-15)。

        规则：
        - 高潜力类目：12-15分
        - 中潜力类目：8-11分
        - 其他/未知：3-7分
        """
        if not category:
            return 3.0

        category_lower = category.lower()

        for cat in HIGH_POTENTIAL_CATEGORIES:
            if cat in category_lower:
                return 15.0

        for cat in MEDIUM_POTENTIAL_CATEGORIES:
            if cat in category_lower:
                return 10.0

        return 5.0

    def _score_newness(self, first_seen_time: datetime | None) -> float:
        """新品程度评分 (0-25)。

        规则：
        - 24小时内发现：25分（最新）
        - 1-3天：20分
        - 3-7天：15分
        - 7-30天：10分
        - >30天：5分
        """
        if not first_seen_time:
            return 5.0

        now = datetime.now()
        age = now - first_seen_time

        if age < timedelta(hours=24):
            return 25.0
        elif age < timedelta(days=3):
            return 20.0
        elif age < timedelta(days=7):
            return 15.0
        elif age < timedelta(days=30):
            return 10.0
        else:
            return 5.0

    def _score_completeness(self, product: Product) -> float:
        """数据完整度评分 (0-10)。

        规则：
        检查关键字段是否完整：
        - name: 2分
        - url: 2分
        - image: 2分
        - price: 2分
        - shop: 2分
        """
        score = 0.0

        if product.name:
            score += 2.0
        if product.url:
            score += 2.0
        if product.image:
            score += 2.0
        if product.price and product.price > 0:
            score += 2.0
        if product.shop:
            score += 2.0

        return score

    def _get_recommend_level(self, total_score: float) -> str:
        """根据总分确定推荐等级。

        规则：
        - 90-100: ★★★★★ 强烈关注
        - 75-89: ★★★★ 推荐关注
        - 60-74: ★★★ 观察
        - <60: 暂不推荐
        """
        if total_score >= 90:
            return RECOMMEND_STRONG
        elif total_score >= 75:
            return RECOMMEND_WATCH
        elif total_score >= 60:
            return RECOMMEND_OBSERVE
        else:
            return RECOMMEND_SKIP
