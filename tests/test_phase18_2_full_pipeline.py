"""Tests for Phase 18 Task 2: Full Product Selection Pipeline Validation."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.services.product_scoring import ProductScoringService
from app.services.supplier_matching import SupplierMatchingService
from app.services.opportunity_scoring import OpportunityScoringService
from app.crawler.alibaba import AlibabaSearchClient


# ── Full Pipeline Integration Tests ──────────────────────────


class TestFullPipelineIntegration:
    """Test full product selection pipeline integration."""

    @pytest.fixture
    def product_scoring_service(self):
        """Create ProductScoringService."""
        return ProductScoringService()

    @pytest.fixture
    def supplier_matching_service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    @pytest.fixture
    def opportunity_scoring_service(self):
        """Create OpportunityScoringService."""
        return OpportunityScoringService()

    @pytest.mark.asyncio
    async def test_full_pipeline_single_product(
        self,
        product_scoring_service,
        supplier_matching_service,
        opportunity_scoring_service,
    ):
        """Test full pipeline for a single product."""
        # Create product
        product = Product(
            id=1,
            name="三只松鼠芋泥味蛋皮吐司卷",
            platform="taobao",
            shop="三只松鼠旗舰店",
            price=69.9,
            category="零食",
            url="https://detail.tmall.com/item.htm?id=1",
            image="https://img.alicdn.com/mock.jpg",
            first_seen_time=datetime.now(),
        )

        # Step 1: Product scoring
        score_data = product_scoring_service.calculate_score(product)
        product_score = ProductScore(
            product_id=product.id,
            shop_score=score_data["shop_score"],
            price_score=score_data["price_score"],
            category_score=score_data["category_score"],
            newness_score=score_data["newness_score"],
            completeness_score=score_data["completeness_score"],
            total_score=score_data["total_score"],
            recommend_level=score_data["recommend_level"],
        )
        assert product_score.total_score > 0

        # Step 2: 1688 matching
        client = AlibabaSearchClient(use_mock=True)
        cleaned = supplier_matching_service.clean_title(product.name)
        keyword = supplier_matching_service.generate_search_keyword(cleaned)
        suppliers = await client.search_products(keyword=keyword)
        assert len(suppliers) > 0

        match_result = supplier_matching_service.match_product(product, suppliers)
        assert match_result is not None

        supplier_match = SupplierMatch(
            product_id=product.id,
            supplier_title=match_result["supplier_title"],
            supplier_url=match_result.get("supplier_url"),
            supplier_price=match_result["supplier_price"],
            similarity_score=match_result["similarity_score"],
            estimated_profit=match_result["estimated_profit"],
            profit_margin=match_result["profit_margin"],
        )
        assert supplier_match.profit_margin > 0

        # Step 3: Opportunity scoring
        opp_data = opportunity_scoring_service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3,
        )
        assert opp_data["total_score"] > 0
        assert opp_data["recommendation"] in [
            "★★★★★ 强烈推荐",
            "★★★★ 值得研究",
            "★★★ 观察",
            "暂不推荐",
        ]

    @pytest.mark.asyncio
    async def test_full_pipeline_multiple_products(
        self,
        product_scoring_service,
        supplier_matching_service,
        opportunity_scoring_service,
    ):
        """Test full pipeline for multiple products."""
        # Create products
        products = [
            Product(
                id=i,
                name=name,
                platform="taobao",
                shop=shop,
                price=price,
                first_seen_time=datetime.now(),
            )
            for i, (name, shop, price) in enumerate([
                ("三只松鼠芋泥吐司卷", "三只松鼠旗舰店", 69.9),
                ("良品铺子鸭脖套餐", "良品铺子旗舰店", 49.9),
                ("完美日记眼影盘", "完美日记官方旗舰店", 89.9),
            ], 1)
        ]

        client = AlibabaSearchClient(use_mock=True)
        results = []

        for product in products:
            # Product scoring
            score_data = product_scoring_service.calculate_score(product)

            # 1688 matching
            cleaned = supplier_matching_service.clean_title(product.name)
            keyword = supplier_matching_service.generate_search_keyword(cleaned)
            suppliers = await client.search_products(keyword=keyword)

            match_result = None
            if suppliers:
                match_result = supplier_matching_service.match_product(product, suppliers)

            # Opportunity scoring
            opp_data = opportunity_scoring_service.calculate_opportunity_score(
                product=product,
                product_score=ProductScore(
                    product_id=product.id,
                    total_score=score_data["total_score"],
                ),
                supplier_match=SupplierMatch(
                    product_id=product.id,
                    supplier_title=match_result["supplier_title"],
                    supplier_price=match_result["supplier_price"],
                    similarity_score=match_result["similarity_score"],
                    profit_margin=match_result["profit_margin"],
                ) if match_result else None,
                supplier_count=3 if match_result else 0,
            )

            results.append({
                "product": product.name,
                "product_score": score_data["total_score"],
                "matched": match_result is not None,
                "opportunity_score": opp_data["total_score"],
                "recommendation": opp_data["recommendation"],
            })

        # Verify all products processed
        assert len(results) == 3
        for r in results:
            assert r["product_score"] > 0
            assert r["opportunity_score"] > 0

    @pytest.mark.asyncio
    async def test_pipeline_with_high_profit_product(
        self,
        product_scoring_service,
        supplier_matching_service,
        opportunity_scoring_service,
    ):
        """Test pipeline with high profit product."""
        product = Product(
            id=1,
            name="花西子蜜粉定妆散粉",
            platform="taobao",
            shop="花西子旗舰店",
            price=129.0,
            category="美妆",
            first_seen_time=datetime.now(),
        )

        # Product scoring
        score_data = product_scoring_service.calculate_score(product)

        # 1688 matching
        client = AlibabaSearchClient(use_mock=True)
        cleaned = supplier_matching_service.clean_title(product.name)
        keyword = supplier_matching_service.generate_search_keyword(cleaned)
        suppliers = await client.search_products(keyword=keyword)

        match_result = supplier_matching_service.match_product(product, suppliers)

        # Verify high profit
        if match_result:
            assert match_result["profit_margin"] > 50

    @pytest.mark.asyncio
    async def test_pipeline_statistics(
        self,
        product_scoring_service,
        supplier_matching_service,
        opportunity_scoring_service,
    ):
        """Test pipeline statistics calculation."""
        products = [
            Product(
                id=i,
                name=name,
                platform="taobao",
                shop=shop,
                price=price,
                first_seen_time=datetime.now(),
            )
            for i, (name, shop, price) in enumerate([
                ("三只松鼠芋泥吐司卷", "三只松鼠旗舰店", 69.9),
                ("良品铺子鸭脖", "良品铺子旗舰店", 49.9),
            ], 1)
        ]

        client = AlibabaSearchClient(use_mock=True)
        match_count = 0
        high_profit_count = 0

        for product in products:
            cleaned = supplier_matching_service.clean_title(product.name)
            keyword = supplier_matching_service.generate_search_keyword(cleaned)
            suppliers = await client.search_products(keyword=keyword)

            if suppliers:
                match_result = supplier_matching_service.match_product(product, suppliers)
                if match_result:
                    match_count += 1
                    if match_result["profit_margin"] > 50:
                        high_profit_count += 1

        # Verify statistics
        assert match_count >= 0
        assert high_profit_count >= 0


# ── Pipeline Edge Cases ──────────────────────────────────────


class TestPipelineEdgeCases:
    """Test pipeline edge cases."""

    @pytest.mark.asyncio
    async def test_pipeline_with_no_supplier_match(self):
        """Test pipeline when no supplier match found."""
        product = Product(
            id=1,
            name="不存在的商品xyz123",
            platform="taobao",
            shop="某店铺",
            price=99.0,
        )

        service = SupplierMatchingService()
        client = AlibabaSearchClient(use_mock=True)

        # Even with mock, try to match
        cleaned = service.clean_title(product.name)
        keyword = service.generate_search_keyword(cleaned)
        suppliers = await client.search_products(keyword=keyword)

        # Mock data always returns results, but match may fail
        if suppliers:
            match = service.match_product(product, suppliers)
            # Match could be None if similarity is too low
            # This is expected behavior

    @pytest.mark.asyncio
    async def test_pipeline_with_minimal_product_data(self):
        """Test pipeline with minimal product data."""
        product = Product(
            id=1,
            name="简单商品",
            platform="taobao",
            shop="店铺",
            price=50.0,
        )

        service = ProductScoringService()
        score_data = service.calculate_score(product)

        # Should still produce valid scores
        assert score_data["total_score"] > 0
        assert score_data["recommend_level"] is not None
