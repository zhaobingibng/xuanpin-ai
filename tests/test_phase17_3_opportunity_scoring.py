"""Tests for Phase 17 Task 3: Opportunity Scoring Model."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.services.opportunity_scoring import (
    OpportunityScoringService,
    RECOMMEND_STRONG,
    RECOMMEND_WORTH,
    RECOMMEND_OBSERVE,
    RECOMMEND_SKIP,
)


# ── OpportunityScore Model Tests ─────────────────────────────


class TestOpportunityScoreModel:
    """Test OpportunityScore model."""

    def test_create_score(self):
        """Test creating an OpportunityScore record."""
        score = OpportunityScore(
            product_id=1,
            new_product_score=20.0,
            shop_score=18.0,
            supplier_score=20.0,
            profit_score=15.0,
            competition_score=10.0,
            total_score=83.0,
            recommendation=RECOMMEND_WORTH,
        )
        assert score.product_id == 1
        assert score.total_score == 83.0
        assert score.recommendation == RECOMMEND_WORTH

    def test_stars_property(self):
        """Test stars property."""
        score = OpportunityScore(
            product_id=1,
            total_score=95.0,
            recommendation=RECOMMEND_STRONG,
        )
        assert score.stars == "★★★★★"


# ── OpportunityScoringService Tests ──────────────────────────


class TestOpportunityScoringService:
    """Test OpportunityScoringService."""

    @pytest.fixture
    def service(self):
        """Create OpportunityScoringService."""
        return OpportunityScoringService()

    def _make_product(self, **kwargs) -> Product:
        """Helper to create a Product with defaults."""
        defaults = {
            "name": "测试商品",
            "platform": "taobao",
            "shop": "测试店铺",
            "price": 99.9,
        }
        defaults.update(kwargs)
        return Product(**defaults)

    def _make_product_score(self, total_score: float) -> ProductScore:
        """Helper to create a ProductScore."""
        return ProductScore(
            product_id=1,
            total_score=total_score,
            recommend_level="推荐",
        )

    def _make_supplier_match(
        self,
        similarity_score: float = 80.0,
        profit_margin: float = 60.0,
    ) -> SupplierMatch:
        """Helper to create a SupplierMatch."""
        return SupplierMatch(
            product_id=1,
            supplier_title="供应商商品",
            supplier_price=20.0,
            similarity_score=similarity_score,
            profit_margin=profit_margin,
        )

    # ── 高利润商品 ─────────────────────────────────────────

    def test_high_profit_product(self, service):
        """Test scoring a high profit product."""
        product = self._make_product(shop="官方旗舰店")
        product_score = self._make_product_score(total_score=85.0)
        supplier_match = self._make_supplier_match(
            similarity_score=85.0,
            profit_margin=75.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3,
        )

        # 新品价值: 25 (>=75)
        assert result["new_product_score"] == 25.0
        # 店铺质量: 20 (官方旗舰店)
        assert result["shop_score"] == 20.0
        # 供应链能力: 25 (相似度>80: 15, 利润率>50: 10)
        assert result["supplier_score"] == 25.0
        # 利润空间: 20 (>70%)
        assert result["profit_score"] == 20.0
        # 竞争情况: 10 (<5个供应商)
        assert result["competition_score"] == 10.0
        # 总分: 100
        assert result["total_score"] == 100.0
        assert result["recommendation"] == RECOMMEND_STRONG

    # ── 低利润商品 ─────────────────────────────────────────

    def test_low_profit_product(self, service):
        """Test scoring a low profit product."""
        product = self._make_product(shop="普通小店")
        product_score = self._make_product_score(total_score=25.0)  # <30
        supplier_match = self._make_supplier_match(
            similarity_score=45.0,
            profit_margin=20.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=30,
        )

        # 新品价值: 5 (<30)
        assert result["new_product_score"] == 5.0
        # 店铺质量: 8 (普通)
        assert result["shop_score"] == 8.0
        # 供应链能力: 10 (相似度40-60: 8, 利润率<20: 2)
        assert result["supplier_score"] == 10.0
        # 利润空间: 5 (<30%)
        assert result["profit_score"] == 5.0
        # 竞争情况: 5 (>20个供应商)
        assert result["competition_score"] == 5.0
        # 总分: 33
        assert result["total_score"] == 33.0
        assert result["recommendation"] == RECOMMEND_SKIP

    # ── 高匹配商品 ─────────────────────────────────────────

    def test_high_match_product(self, service):
        """Test scoring a high match product."""
        product = self._make_product(shop="品牌旗舰店")
        product_score = self._make_product_score(total_score=70.0)
        supplier_match = self._make_supplier_match(
            similarity_score=90.0,
            profit_margin=55.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=8,
        )

        # 新品价值: 20 (60-74)
        assert result["new_product_score"] == 20.0
        # 店铺质量: 18 (旗舰店)
        assert result["shop_score"] == 18.0
        # 供应链能力: 25 (相似度>80: 15, 利润率>50: 10)
        assert result["supplier_score"] == 25.0
        # 利润空间: 15 (50-70%)
        assert result["profit_score"] == 15.0
        # 竞争情况: 7 (5-20个供应商)
        assert result["competition_score"] == 7.0
        # 总分: 85
        assert result["total_score"] == 85.0
        assert result["recommendation"] == RECOMMEND_WORTH

    # ── 低匹配商品 ─────────────────────────────────────────

    def test_low_match_product(self, service):
        """Test scoring a low match product."""
        product = self._make_product(shop="普通店铺")
        product_score = self._make_product_score(total_score=45.0)
        supplier_match = self._make_supplier_match(
            similarity_score=35.0,
            profit_margin=25.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=15,
        )

        # 新品价值: 10 (30-49)
        assert result["new_product_score"] == 10.0
        # 店铺质量: 8 (普通)
        assert result["shop_score"] == 8.0
        # 供应链能力: 10 (相似度30-40: 5, 利润率20-30: 5)
        assert result["supplier_score"] == 10.0
        # 利润空间: 5 (<30%)
        assert result["profit_score"] == 5.0
        # 竞争情况: 7 (5-20个供应商)
        assert result["competition_score"] == 7.0
        # 总分: 40
        assert result["total_score"] == 40.0
        assert result["recommendation"] == RECOMMEND_SKIP

    # ── 推荐等级判断 ───────────────────────────────────────

    def test_recommendation_strong(self, service):
        """Test recommendation level: strongly recommend (90-100)."""
        product = self._make_product(shop="官方旗舰店")
        product_score = self._make_product_score(total_score=90.0)
        supplier_match = self._make_supplier_match(
            similarity_score=95.0,
            profit_margin=80.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=2,
        )

        assert result["total_score"] >= 90
        assert result["recommendation"] == RECOMMEND_STRONG

    def test_recommendation_worth(self, service):
        """Test recommendation level: worth research (75-89)."""
        product = self._make_product(shop="旗舰店")
        product_score = self._make_product_score(total_score=65.0)
        supplier_match = self._make_supplier_match(
            similarity_score=70.0,
            profit_margin=55.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=10,
        )

        assert 75 <= result["total_score"] < 90
        assert result["recommendation"] == RECOMMEND_WORTH

    def test_recommendation_observe(self, service):
        """Test recommendation level: observe (60-74)."""
        product = self._make_product(shop="专卖店")
        product_score = self._make_product_score(total_score=55.0)
        supplier_match = self._make_supplier_match(
            similarity_score=50.0,
            profit_margin=40.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=12,
        )

        assert 60 <= result["total_score"] < 75
        assert result["recommendation"] == RECOMMEND_OBSERVE

    def test_recommendation_skip(self, service):
        """Test recommendation level: skip (<60)."""
        product = self._make_product(shop="无名小店")
        product_score = self._make_product_score(total_score=20.0)
        supplier_match = self._make_supplier_match(
            similarity_score=25.0,
            profit_margin=15.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=50,
        )

        assert result["total_score"] < 60
        assert result["recommendation"] == RECOMMEND_SKIP

    # ── 无数据情况 ─────────────────────────────────────────

    def test_no_product_score(self, service):
        """Test scoring without product score."""
        product = self._make_product()

        result = service.calculate_opportunity_score(
            product=product,
            product_score=None,
            supplier_match=None,
            supplier_count=0,
        )

        # 默认新品价值: 10
        assert result["new_product_score"] == 10.0
        # 无供应链匹配: 0
        assert result["supplier_score"] == 0.0

    def test_no_supplier_match(self, service):
        """Test scoring without supplier match."""
        product = self._make_product()
        product_score = self._make_product_score(total_score=70.0)

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=None,
            supplier_count=0,
        )

        # 无供应链匹配: 0
        assert result["supplier_score"] == 0.0
        # 默认利润: 5
        assert result["profit_score"] == 5.0

    # ── create_score_record ────────────────────────────────

    def test_create_score_record(self, service):
        """Test creating an OpportunityScore record."""
        product = self._make_product(id=1, shop="官方旗舰店")
        product_score = self._make_product_score(total_score=85.0)
        supplier_match = self._make_supplier_match(
            similarity_score=85.0,
            profit_margin=75.0,
        )

        record = service.create_score_record(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3,
        )

        assert isinstance(record, OpportunityScore)
        assert record.product_id == 1
        assert record.total_score == 100.0
        assert record.recommendation == RECOMMEND_STRONG


# ── TaobaoCrawler Integration Tests ──────────────────────────


class TestTaobaoCrawlerOpportunityScoring:
    """Test TaobaoCrawler opportunity scoring integration."""

    @pytest.fixture
    def crawler(self):
        from unittest.mock import patch
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)

            from app.crawler.taobao import TaobaoCrawler
            return TaobaoCrawler()

    @pytest.mark.asyncio
    async def test_calculate_opportunity_scores_empty(self, crawler):
        """Test scoring when no new products."""
        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=[])

        mock_service = MagicMock()

        result = await crawler.calculate_opportunity_scores(mock_repo, mock_service)

        assert result["total"] == 0
        assert result["scored_count"] == 0

    @pytest.mark.asyncio
    async def test_calculate_opportunity_scores_success(self, crawler):
        """Test successful opportunity scoring flow."""
        from datetime import datetime

        mock_products = [
            Product(
                id=1,
                name="高价值新品",
                platform="taobao",
                shop="官方旗舰店",
                price=99.0,
                first_seen_time=datetime.now(),
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=mock_products)
        mock_repo._session = AsyncMock()
        mock_repo._session.add_all = MagicMock()

        mock_service = MagicMock()
        mock_service.create_score_record.return_value = OpportunityScore(
            product_id=1,
            total_score=95.0,
            recommendation=RECOMMEND_STRONG,
        )

        result = await crawler.calculate_opportunity_scores(mock_repo, mock_service)

        assert result["total"] == 1
        assert result["scored_count"] == 1


# ── Example Recommendation Case ──────────────────────────────


class TestExampleRecommendationCase:
    """Test a complete example recommendation case."""

    def test_full_example(self):
        """Test complete example: 高利润跟卖机会.

        淘宝商品: 某美妆旗舰店 爆款面膜
        售价: 89元

        新品评分: 85分 (高)
        1688匹配: 相似度85%, 利润率75%
        供应商数量: 3家

        预期结果:
        - 总分: 100分
        - 推荐: ★★★★★ 强烈推荐
        """
        service = OpportunityScoringService()

        product = Product(
            id=1,
            name="爆款面膜补水保湿",
            platform="taobao",
            shop="美妆官方旗舰店",
            price=89.0,
        )

        product_score = ProductScore(
            product_id=1,
            total_score=85.0,
            recommend_level="★★★★ 推荐关注",
        )

        supplier_match = SupplierMatch(
            product_id=1,
            supplier_title="面膜补水保湿 厂家直销",
            supplier_price=22.0,
            similarity_score=85.0,
            profit_margin=75.0,
        )

        result = service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3,
        )

        # 验证各维度评分
        assert result["new_product_score"] == 25.0  # 高新品评分
        assert result["shop_score"] == 20.0  # 官方旗舰店
        assert result["supplier_score"] == 25.0  # 高匹配+高利润
        assert result["profit_score"] == 20.0  # 利润率>70%
        assert result["competition_score"] == 10.0  # 供应商<5

        # 总分100
        assert result["total_score"] == 100.0
        assert result["recommendation"] == RECOMMEND_STRONG

        # 创建记录
        record = service.create_score_record(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3,
        )
        assert record.total_score == 100.0
