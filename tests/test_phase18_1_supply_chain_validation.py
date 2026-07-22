"""Tests for Phase 18 Task 1: 1688 Supply Chain Search Validation."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.crawler.alibaba import AlibabaSearchClient
from app.crawler.alibaba_1688 import SupplierProduct
from app.models.product import Product
from app.services.supplier_matching import SupplierMatchingService


# ── 1688 Search Parsing Tests ────────────────────────────────


class TestAlibabaSearchParsing:
    """Test 1688 search result parsing."""

    @pytest.mark.asyncio
    async def test_real_search_returns_full_data(self):
        """Test real search returns complete data."""
        # Mock crawler with SupplierProduct
        mock_crawler = MagicMock()
        mock_crawler.search_suppliers = AsyncMock(return_value=[
            SupplierProduct(
                product_id="abc123",
                title="芋泥蛋皮吐司卷 厂家直销",
                price=18.0,
                supplier_name="某某食品厂",
                image_url="https://cbu01.alicdn.com/img/xxx.jpg",
                url="https://detail.1688.com/offer/123.html",
            ),
        ])

        client = AlibabaSearchClient(crawler=mock_crawler)
        results = await client.search_products("芋泥蛋皮吐司卷")

        assert len(results) == 1
        assert results[0]["title"] == "芋泥蛋皮吐司卷 厂家直销"
        assert results[0]["price"] == 18.0
        assert results[0]["supplier_name"] == "某某食品厂"
        assert results[0]["image_url"] == "https://cbu01.alicdn.com/img/xxx.jpg"

    @pytest.mark.asyncio
    async def test_mock_search_returns_full_data(self):
        """Test mock search returns complete data."""
        client = AlibabaSearchClient(use_mock=True)
        results = await client.search_products("芋泥蛋皮吐司卷")

        assert len(results) > 0
        assert "title" in results[0]
        assert "price" in results[0]
        assert "supplier_name" in results[0]
        assert "image_url" in results[0]

    @pytest.mark.asyncio
    async def test_search_with_empty_result(self):
        """Test search with empty result."""
        mock_crawler = MagicMock()
        mock_crawler.search_suppliers = AsyncMock(return_value=[])

        client = AlibabaSearchClient(crawler=mock_crawler)
        results = await client.search_products("不存在的商品")

        assert results == []


# ── Title Processing Tests ───────────────────────────────────


class TestTitleProcessing:
    """Test title processing for 1688 search."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_clean_taobao_title(self, service):
        """Test cleaning Taobao title for 1688 search.

        Example:
        淘宝: 三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点
        转换: 芋泥蛋皮吐司卷
        """
        original = "三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点"
        cleaned = service.clean_title(original)

        # Brand should be removed
        assert "三只松鼠" not in cleaned
        # Core product name should remain
        assert "芋泥" in cleaned or "蛋皮" in cleaned

    def test_generate_search_keyword(self, service):
        """Test generating 1688 search keyword."""
        cleaned = "芋泥蛋皮吐司卷"
        keyword = service.generate_search_keyword(cleaned)

        assert len(keyword) > 0
        # Should be suitable for 1688 search
        assert len(keyword) >= 3

    def test_complex_title_cleaning(self, service):
        """Test complex title cleaning."""
        original = "良品铺子芒果干100g袋装蜜饯果脯零食小吃"
        cleaned = service.clean_title(original)

        # Brand removed
        assert "良品铺子" not in cleaned
        # Number specs removed
        assert "100g" not in cleaned


# ── Matching Tests ───────────────────────────────────────────


class TestSupplyChainMatching:
    """Test supply chain matching."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_match_with_real_supplier_data(self, service):
        """Test matching with realistic supplier data."""
        product = Product(
            id=1,
            name="芋泥味蛋皮吐司卷肉松夹心面包",
            platform="taobao",
            shop="某旗舰店",
            price=69.0,
        )

        # Realistic 1688 supplier data
        supplier_products = [
            {
                "title": "芋泥蛋皮吐司卷肉松面包 厂家直销批发",
                "url": "https://detail.1688.com/offer/123456.html",
                "image_url": "https://cbu01.alicdn.com/img/xxx.jpg",
                "price": 18.0,
                "supplier_name": "某某食品厂",
            },
            {
                "title": "肉松面包 早餐蛋糕 工厂货源",
                "url": "https://detail.1688.com/offer/789012.html",
                "image_url": "https://cbu01.alicdn.com/img/yyy.jpg",
                "price": 15.0,
                "supplier_name": "某某烘焙批发",
            },
        ]

        result = service.match_product(product, supplier_products)

        assert result is not None
        assert result["supplier_price"] > 0
        assert result["similarity_score"] > 0
        assert result["profit_margin"] > 0
        assert result["estimated_profit"] > 0

    def test_profit_calculation_accuracy(self, service):
        """Test profit calculation accuracy.

        Example:
        售价: 69元
        成本: 18元
        利润率: (69-18)/69 * 100 = 73.9%
        """
        result = service.calculate_profit(sell_price=69.0, cost_price=18.0)

        assert result["estimated_profit"] == 51.0
        assert result["profit_margin"] == 73.9


# ── Integration Tests ────────────────────────────────────────


class TestSupplyChainIntegration:
    """Test supply chain integration."""

    @pytest.mark.asyncio
    async def test_full_matching_flow_with_mock(self):
        """Test full matching flow with mock data."""
        # Setup
        service = SupplierMatchingService()
        client = AlibabaSearchClient(use_mock=True)

        product = Product(
            id=1,
            name="三只松鼠芋泥味蛋皮吐司卷",
            platform="taobao",
            shop="三只松鼠旗舰店",
            price=69.0,
        )

        # Step 1: Clean title
        cleaned = service.clean_title(product.name)
        assert "三只松鼠" not in cleaned

        # Step 2: Generate keyword
        keyword = service.generate_search_keyword(cleaned)
        assert len(keyword) > 0

        # Step 3: Search 1688
        suppliers = await client.search_products(keyword)
        assert len(suppliers) > 0

        # Step 4: Match
        result = service.match_product(product, suppliers)

        # Result should have all required fields
        if result:
            assert "supplier_title" in result
            assert "supplier_price" in result
            assert "similarity_score" in result
            assert "profit_margin" in result
            assert "estimated_profit" in result


# ── Example Match Case ───────────────────────────────────────


class TestExampleMatchCase:
    """Test example match case for validation report."""

    @pytest.mark.asyncio
    async def test_example_product_matching(self):
        """Test example product matching for validation.

        商品: 三只松鼠芋泥味蛋皮吐司卷
        淘宝价格: 69元

        预期:
        - 找到1688供应商
        - 利润率 > 50%
        """
        service = SupplierMatchingService()
        client = AlibabaSearchClient(use_mock=True)

        product = Product(
            id=1,
            name="三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点",
            platform="taobao",
            shop="三只松鼠旗舰店",
            price=69.0,
        )

        # Clean and search
        cleaned = service.clean_title(product.name)
        keyword = service.generate_search_keyword(cleaned)
        suppliers = await client.search_products(keyword)

        # Match
        result = service.match_product(product, suppliers)

        # Verify
        assert result is not None
        assert result["supplier_price"] < product.price  # Cost should be lower
        assert result["profit_margin"] > 50.0  # Should have good margin
        assert result["estimated_profit"] > 30.0  # Should have good profit
