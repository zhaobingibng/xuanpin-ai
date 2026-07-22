"""Opportunity Scoring Service — 跟卖机会指数评分服务.

评分维度（总分100）：
1. 新品价值 (0-25): 来源 ProductScore
2. 店铺质量 (0-20): 来源 店铺等级
3. 供应链能力 (0-25): 来源 SupplierMatch
4. 利润空间 (0-20): 来源利润率
5. 竞争情况 (0-10): 来源供应商数量

推荐等级：
- 90-100: ★★★★★ 强烈推荐
- 75-89: ★★★★ 值得研究
- 60-74: ★★★ 观察
- <60: 暂不推荐
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.models.opportunity_score import OpportunityScore
from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch


# ── 推荐等级常量 ─────────────────────────────────────────────

RECOMMEND_STRONG = "★★★★★ 强烈推荐"
RECOMMEND_WORTH = "★★★★ 值得研究"
RECOMMEND_OBSERVE = "★★★ 观察"
RECOMMEND_SKIP = "暂不推荐"


class OpportunityScoringService:
    """跟卖机会指数评分服务。

    综合评估一个商品是否值得跟卖，结合：
    - 新品价值（是否值得跟进）
    - 店铺质量（竞争对手实力）
    - 供应链能力（能否找到货源）
    - 利润空间（能否赚钱）
    - 竞争情况（市场竞争程度）

    Usage::

        service = OpportunityScoringService()
        score = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=5,
        )
        # score = {
        #     "new_product_score": 20.0,
        #     "shop_score": 18.0,
        #     "supplier_score": 20.0,
        #     "profit_score": 15.0,
        #     "competition_score": 10.0,
        #     "total_score": 83.0,
        #     "recommendation": "★★★★ 值得研究",
        # }
    """

    # ── 评分维度最大值 ──────────────────────────────────────

    MAX_NEW_PRODUCT_SCORE = 25
    MAX_SHOP_SCORE = 20
    MAX_SUPPLIER_SCORE = 25
    MAX_PROFIT_SCORE = 20
    MAX_COMPETITION_SCORE = 10

    # ── Public API ──────────────────────────────────────────

    def calculate_opportunity_score(
        self,
        product: Product,
        product_score: ProductScore | None = None,
        supplier_match: SupplierMatch | None = None,
        supplier_count: int = 0,
    ) -> dict[str, Any]:
        """计算跟卖机会指数。

        Args:
            product: 商品 ORM 实例。
            product_score: 新品价值评分（可选）。
            supplier_match: 供应链匹配结果（可选）。
            supplier_count: 供应商数量。

        Returns:
            Dict with scoring details.
        """
        # 1. 新品价值评分 (0-25)
        new_product_score = self._score_new_product(product_score)

        # 2. 店铺质量评分 (0-20)
        shop_score = self._score_shop_quality(product.shop)

        # 3. 供应链能力评分 (0-25)
        supplier_score = self._score_supplier_capability(supplier_match)

        # 4. 利润空间评分 (0-20)
        profit_score = self._score_profit_margin(supplier_match)

        # 5. 竞争情况评分 (0-10)
        competition_score = self._score_competition(supplier_count)

        # 总分
        total_score = (
            new_product_score + shop_score + supplier_score +
            profit_score + competition_score
        )

        # 推荐等级
        recommendation = self._get_recommendation(total_score)

        return {
            "new_product_score": new_product_score,
            "shop_score": shop_score,
            "supplier_score": supplier_score,
            "profit_score": profit_score,
            "competition_score": competition_score,
            "total_score": total_score,
            "recommendation": recommendation,
        }

    def create_score_record(
        self,
        product: Product,
        product_score: ProductScore | None = None,
        supplier_match: SupplierMatch | None = None,
        supplier_count: int = 0,
    ) -> OpportunityScore:
        """创建跟卖机会评分记录。

        Args:
            product: 商品 ORM 实例。
            product_score: 新品价值评分（可选）。
            supplier_match: 供应链匹配结果（可选）。
            supplier_count: 供应商数量。

        Returns:
            OpportunityScore ORM 实例。
        """
        score_data = self.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=supplier_count,
        )

        return OpportunityScore(
            product_id=product.id,
            new_product_score=score_data["new_product_score"],
            shop_score=score_data["shop_score"],
            supplier_score=score_data["supplier_score"],
            profit_score=score_data["profit_score"],
            competition_score=score_data["competition_score"],
            total_score=score_data["total_score"],
            recommendation=score_data["recommendation"],
        )

    # ── 内部评分方法 ────────────────────────────────────────

    def _score_new_product(self, product_score: ProductScore | None) -> float:
        """新品价值评分 (0-25)。

        来源：ProductScore.total_score

        规则：
        - 高新品评分 (>=75): 25分
        - 中 (50-74): 15-20分
        - 低 (<50): 5-10分
        """
        if not product_score:
            return 10.0  # 默认中等偏低

        total = product_score.total_score

        if total >= 75:
            return 25.0
        elif total >= 60:
            return 20.0
        elif total >= 50:
            return 15.0
        elif total >= 30:
            return 10.0
        else:
            return 5.0

    def _score_shop_quality(self, shop_name: str | None) -> float:
        """店铺质量评分 (0-20)。

        来源：店铺等级/名称特征

        规则：
        - 官方旗舰店: 20分
        - 旗舰店: 18分
        - 品牌店/专卖: 15分
        - 普通: 5-10分
        """
        if not shop_name:
            return 5.0

        shop_lower = shop_name.lower()

        if "官方" in shop_lower and "旗舰" in shop_lower:
            return 20.0
        elif "旗舰" in shop_lower:
            return 18.0
        elif "专卖" in shop_lower or "品牌" in shop_lower:
            return 15.0
        else:
            return 8.0

    def _score_supplier_capability(self, supplier_match: SupplierMatch | None) -> float:
        """供应链能力评分 (0-25)。

        来源：SupplierMatch

        规则：
        - 匹配度高 (相似度>80): 15分
        - 利润空间高 (利润率>50%): 10分
        - 部分满足: 按比例给分
        """
        if not supplier_match:
            return 0.0

        score = 0.0

        # 匹配度评分 (0-15)
        similarity = supplier_match.similarity_score
        if similarity > 80:
            score += 15.0
        elif similarity > 60:
            score += 12.0
        elif similarity > 40:
            score += 8.0
        elif similarity > 30:
            score += 5.0
        else:
            score += 2.0

        # 利润空间评分 (0-10)
        profit_margin = supplier_match.profit_margin
        if profit_margin > 50:
            score += 10.0
        elif profit_margin > 30:
            score += 7.0
        elif profit_margin > 20:
            score += 5.0
        else:
            score += 2.0

        return score

    def _score_profit_margin(self, supplier_match: SupplierMatch | None) -> float:
        """利润空间评分 (0-20)。

        规则：
        - 利润率 >70%: 20分
        - 50-70%: 15分
        - 30-50%: 10分
        - <30%: 5分
        """
        if not supplier_match:
            return 5.0  # 默认低分

        profit_margin = supplier_match.profit_margin

        if profit_margin > 70:
            return 20.0
        elif profit_margin > 50:
            return 15.0
        elif profit_margin > 30:
            return 10.0
        else:
            return 5.0

    def _score_competition(self, supplier_count: int) -> float:
        """竞争情况评分 (0-10)。

        规则：
        - 供应商数量少 (<5): 10分（竞争少，机会大）
        - 中等 (5-20): 7分
        - 供应商多 (>20): 5分（竞争激烈）
        """
        if supplier_count < 5:
            return 10.0
        elif supplier_count <= 20:
            return 7.0
        else:
            return 5.0

    def _get_recommendation(self, total_score: float) -> str:
        """根据总分确定推荐等级。

        规则：
        - 90-100: ★★★★★ 强烈推荐
        - 75-89: ★★★★ 值得研究
        - 60-74: ★★★ 观察
        - <60: 暂不推荐
        """
        if total_score >= 90:
            return RECOMMEND_STRONG
        elif total_score >= 75:
            return RECOMMEND_WORTH
        elif total_score >= 60:
            return RECOMMEND_OBSERVE
        else:
            return RECOMMEND_SKIP
