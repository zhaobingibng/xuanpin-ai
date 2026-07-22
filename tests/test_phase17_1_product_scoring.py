"""Tests for Phase 17 Task 1: Product Value Scoring Model."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from app.models.product import Product
from app.models.product_score import ProductScore
from app.services.product_scoring import (
    ProductScoringService,
    RECOMMEND_STRONG,
    RECOMMEND_WATCH,
    RECOMMEND_OBSERVE,
    RECOMMEND_SKIP,
)


# ── ProductScore Model Tests ─────────────────────────────────


class TestProductScoreModel:
    """Test ProductScore model."""

    def test_create_score(self):
        """Test creating a ProductScore record."""
        score = ProductScore(
            product_id=1,
            shop_score=25.0,
            price_score=15.0,
            category_score=10.0,
            newness_score=20.0,
            completeness_score=8.0,
            total_score=78.0,
            recommend_level=RECOMMEND_WATCH,
        )
        assert score.product_id == 1
        assert score.total_score == 78.0
        assert score.recommend_level == RECOMMEND_WATCH

    def test_stars_property(self):
        """Test stars property."""
        score = ProductScore(
            product_id=1,
            total_score=95.0,
            recommend_level=RECOMMEND_STRONG,
        )
        assert score.stars == "★★★★★"

    def test_stars_watch(self):
        """Test stars for watch level."""
        score = ProductScore(
            product_id=1,
            total_score=80.0,
            recommend_level=RECOMMEND_WATCH,
        )
        assert score.stars == "★★★★"


# ── ProductScoringService Tests ──────────────────────────────


class TestProductScoringService:
    """Test ProductScoringService."""

    @pytest.fixture
    def service(self):
        """Create ProductScoringService."""
        return ProductScoringService()

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

    # ── 高价值新品评分 ─────────────────────────────────────

    def test_high_value_new_product(self, service):
        """Test scoring a high-value new product."""
        product = self._make_product(
            name="爆款美妆产品",
            shop="某某官方旗舰店",
            category="美妆",
            price=89.9,
            url="https://item.taobao.com/item.htm?id=123",
            image="https://img.alicdn.com/xxx.jpg",
            first_seen_time=datetime.now() - timedelta(hours=12),
        )

        result = service.calculate_score(product)

        # 官方旗舰店: 30
        assert result["shop_score"] == 30.0
        # 10-100元: 20
        assert result["price_score"] == 20.0
        # 高潜力类目: 15
        assert result["category_score"] == 15.0
        # 24小时内: 25
        assert result["newness_score"] == 25.0
        # 完整数据: 10
        assert result["completeness_score"] == 10.0
        # 总分: 100
        assert result["total_score"] == 100.0
        assert result["recommend_level"] == RECOMMEND_STRONG

    # ── 普通商品评分 ───────────────────────────────────────

    def test_normal_product(self, service):
        """Test scoring a normal product."""
        product = self._make_product(
            name="普通商品",
            shop="普通小店",
            price=50.0,
            url="https://item.taobao.com/item.htm?id=456",
            first_seen_time=datetime.now() - timedelta(days=5),
        )

        result = service.calculate_score(product)

        # 普通店铺: 10
        assert result["shop_score"] == 10.0
        # 10-100元: 20
        assert result["price_score"] == 20.0
        # 无类目: 3
        assert result["category_score"] == 3.0
        # 3-7天: 15
        assert result["newness_score"] == 15.0
        # 缺少image: 8
        assert result["completeness_score"] == 8.0
        # 总分: 56
        assert result["total_score"] == 56.0
        assert result["recommend_level"] == RECOMMEND_SKIP

    # ── 推荐等级判断 ───────────────────────────────────────

    def test_recommend_level_strong(self, service):
        """Test recommend level: strongly recommend (90-100)."""
        product = self._make_product(
            shop="官方旗舰店",
            category="美妆",
            price=89.9,
            url="https://item.taobao.com/item.htm?id=1",
            image="https://img.alicdn.com/xxx.jpg",
            first_seen_time=datetime.now() - timedelta(hours=6),
        )

        result = service.calculate_score(product)
        assert result["total_score"] >= 90
        assert result["recommend_level"] == RECOMMEND_STRONG

    def test_recommend_level_watch(self, service):
        """Test recommend level: watch (75-89)."""
        product = self._make_product(
            shop="品牌旗舰店",
            category="服饰",
            price=150.0,
            url="https://item.taobao.com/item.htm?id=2",
            first_seen_time=datetime.now() - timedelta(days=2),
        )

        result = service.calculate_score(product)
        # 旗舰店25 + 150元15 + 服饰10 + 2天20 + 8 = 78
        assert 75 <= result["total_score"] < 90
        assert result["recommend_level"] == RECOMMEND_WATCH

    def test_recommend_level_observe(self, service):
        """Test recommend level: observe (60-74)."""
        product = self._make_product(
            shop="专卖店",
            price=200.0,
            url="https://item.taobao.com/item.htm?id=3",
            first_seen_time=datetime.now() - timedelta(days=5),
        )

        result = service.calculate_score(product)
        # 专卖20 + 200元15 + 无类目3 + 5天15 + 8 = 61
        assert 60 <= result["total_score"] < 75
        assert result["recommend_level"] == RECOMMEND_OBSERVE

    def test_recommend_level_skip(self, service):
        """Test recommend level: skip (<60)."""
        product = self._make_product(
            shop="无名小店",
            price=999.0,
            first_seen_time=datetime.now() - timedelta(days=60),
        )

        result = service.calculate_score(product)
        # 无名10 + 999元5 + 无类目3 + 60天5 + 4 = 27
        assert result["total_score"] < 60
        assert result["recommend_level"] == RECOMMEND_SKIP

    # ── 评分计算稳定性 ─────────────────────────────────────

    def test_scoring_stability(self, service):
        """Test scoring stability - same input should give same output."""
        product = self._make_product(
            shop="官方旗舰店",
            category="美妆",
            price=89.9,
            url="https://item.taobao.com/item.htm?id=stable",
            image="https://img.alicdn.com/xxx.jpg",
            first_seen_time=datetime.now() - timedelta(hours=12),
        )

        result1 = service.calculate_score(product)
        result2 = service.calculate_score(product)

        assert result1["total_score"] == result2["total_score"]
        assert result1["recommend_level"] == result2["recommend_level"]

    # ── 各维度评分测试 ─────────────────────────────────────

    def test_shop_score_official_flagship(self, service):
        """Test shop score: official flagship store."""
        product = self._make_product(shop="某某官方旗舰店")
        result = service.calculate_score(product)
        assert result["shop_score"] == 30.0

    def test_shop_score_self_operated(self, service):
        """Test shop score: self-operated store."""
        product = self._make_product(shop="某某自营店")
        result = service.calculate_score(product)
        assert result["shop_score"] == 28.0

    def test_shop_score_flagship(self, service):
        """Test shop score: flagship store."""
        product = self._make_product(shop="某某旗舰店")
        result = service.calculate_score(product)
        assert result["shop_score"] == 25.0

    def test_shop_score_normal(self, service):
        """Test shop score: normal store."""
        product = self._make_product(shop="普通小店")
        result = service.calculate_score(product)
        assert result["shop_score"] == 10.0

    def test_price_score_10_100(self, service):
        """Test price score: 10-100 yuan."""
        product = self._make_product(price=50.0)
        result = service.calculate_score(product)
        assert result["price_score"] == 20.0

    def test_price_score_100_300(self, service):
        """Test price score: 100-300 yuan."""
        product = self._make_product(price=200.0)
        result = service.calculate_score(product)
        assert result["price_score"] == 15.0

    def test_price_score_high(self, service):
        """Test price score: >500 yuan."""
        product = self._make_product(price=999.0)
        result = service.calculate_score(product)
        assert result["price_score"] == 5.0

    def test_category_score_high_potential(self, service):
        """Test category score: high potential category."""
        product = self._make_product(category="美妆护肤")
        result = service.calculate_score(product)
        assert result["category_score"] == 15.0

    def test_category_score_medium_potential(self, service):
        """Test category score: medium potential category."""
        product = self._make_product(category="数码产品")
        result = service.calculate_score(product)
        assert result["category_score"] == 10.0

    def test_newness_score_24h(self, service):
        """Test newness score: within 24 hours."""
        product = self._make_product(first_seen_time=datetime.now() - timedelta(hours=12))
        result = service.calculate_score(product)
        assert result["newness_score"] == 25.0

    def test_newness_score_3_days(self, service):
        """Test newness score: 1-3 days."""
        product = self._make_product(first_seen_time=datetime.now() - timedelta(days=2))
        result = service.calculate_score(product)
        assert result["newness_score"] == 20.0

    def test_newness_score_7_days(self, service):
        """Test newness score: 3-7 days."""
        product = self._make_product(first_seen_time=datetime.now() - timedelta(days=5))
        result = service.calculate_score(product)
        assert result["newness_score"] == 15.0

    def test_newness_score_old(self, service):
        """Test newness score: >30 days."""
        product = self._make_product(first_seen_time=datetime.now() - timedelta(days=60))
        result = service.calculate_score(product)
        assert result["newness_score"] == 5.0

    # ── create_score_record ────────────────────────────────

    def test_create_score_record(self, service):
        """Test creating a ProductScore record."""
        product = self._make_product(
            id=1,
            shop="官方旗舰店",
            category="美妆",
            price=89.9,
            url="https://item.taobao.com/item.htm?id=1",
            image="https://img.alicdn.com/xxx.jpg",
            first_seen_time=datetime.now() - timedelta(hours=12),
        )

        score_record = service.create_score_record(product)

        assert isinstance(score_record, ProductScore)
        assert score_record.product_id == 1
        assert score_record.total_score == 100.0
        assert score_record.recommend_level == RECOMMEND_STRONG


# ── TaobaoCrawler Integration Tests ──────────────────────────


class TestTaobaoCrawlerScoring:
    """Test TaobaoCrawler scoring integration."""

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
    async def test_score_new_products_empty(self, crawler):
        """Test scoring when no new products."""
        from unittest.mock import AsyncMock

        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=[])

        mock_service = MagicMock()

        result = await crawler.score_new_products(mock_repo, mock_service)

        assert result["total"] == 0
        assert result["scored_count"] == 0

    @pytest.mark.asyncio
    async def test_score_new_products(self, crawler):
        """Test scoring new products."""
        from unittest.mock import AsyncMock

        mock_products = [
            Product(
                id=1,
                name="新品1",
                platform="taobao",
                shop="官方旗舰店",
                price=99.9,
                first_seen_time=datetime.now(),
            ),
            Product(
                id=2,
                name="新品2",
                platform="taobao",
                shop="品牌旗舰店",
                price=199.9,
                first_seen_time=datetime.now(),
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=mock_products)
        mock_repo._session = AsyncMock()
        mock_repo._session.add_all = MagicMock()

        mock_service = MagicMock()
        mock_service.create_score_record = MagicMock(side_effect=[
            ProductScore(product_id=1, total_score=90.0, recommend_level=RECOMMEND_STRONG),
            ProductScore(product_id=2, total_score=75.0, recommend_level=RECOMMEND_WATCH),
        ])

        result = await crawler.score_new_products(mock_repo, mock_service)

        assert result["total"] == 2
        assert result["scored_count"] == 2
        mock_repo._session.add_all.assert_called_once()
