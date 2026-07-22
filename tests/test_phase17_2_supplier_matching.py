"""Tests for Phase 17 Task 2: Taobao → 1688 Supply Chain Matching."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.models.product import Product
from app.models.supplier_match import SupplierMatch
from app.services.supplier_matching import SupplierMatchingService
from app.crawler.alibaba import AlibabaSearchClient


# ── SupplierMatch Model Tests ────────────────────────────────


class TestSupplierMatchModel:
    """Test SupplierMatch model."""

    def test_create_match(self):
        """Test creating a SupplierMatch record."""
        match = SupplierMatch(
            product_id=1,
            supplier_title="芋泥蛋皮吐司卷 厂家直销",
            supplier_url="https://detail.1688.com/offer/123.html",
            supplier_price=18.0,
            similarity_score=85.0,
            estimated_profit=51.0,
            profit_margin=73.9,
        )
        assert match.product_id == 1
        assert match.supplier_price == 18.0
        assert match.profit_margin == 73.9


# ── Title Cleaning Tests ─────────────────────────────────────


class TestTitleCleaning:
    """Test title cleaning functionality."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_clean_title_remove_brand(self, service):
        """Test removing brand words."""
        title = "三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点"
        cleaned = service.clean_title(title)
        assert "三只松鼠" not in cleaned
        assert "芋泥" in cleaned
        assert "蛋皮吐司卷" in cleaned

    def test_clean_title_remove_promo(self, service):
        """Test removing promo words."""
        title = "爆款热卖网红同款面包包邮"
        cleaned = service.clean_title(title)
        assert "爆款" not in cleaned
        assert "热卖" not in cleaned
        assert "包邮" not in cleaned

    def test_clean_title_remove_special_chars(self, service):
        """Test removing special characters."""
        title = "【爆款】蛋皮吐司卷（新品）★推荐★"
        cleaned = service.clean_title(title)
        assert "【" not in cleaned
        assert "】" not in cleaned
        assert "（" not in cleaned
        assert "★" not in cleaned

    def test_clean_title_remove_number_specs(self, service):
        """Test removing number specifications."""
        title = "蛋皮吐司卷500g装10包"
        cleaned = service.clean_title(title)
        assert "500g" not in cleaned
        assert "10包" not in cleaned

    def test_clean_title_empty(self, service):
        """Test cleaning empty title."""
        assert service.clean_title("") == ""
        assert service.clean_title(None) == ""


# ── Keyword Generation Tests ─────────────────────────────────


class TestKeywordGeneration:
    """Test search keyword generation."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_generate_keyword_basic(self, service):
        """Test basic keyword generation."""
        cleaned = "芋泥味蛋皮吐司卷"
        keyword = service.generate_search_keyword(cleaned)
        # Should remove connector words
        assert len(keyword) > 0

    def test_generate_keyword_empty(self, service):
        """Test generating keyword from empty string."""
        assert service.generate_search_keyword("") == ""


# ── Similarity Calculation Tests ─────────────────────────────


class TestSimilarityCalculation:
    """Test similarity calculation."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_high_similarity(self, service):
        """Test high similarity between similar titles."""
        title1 = "芋泥蛋皮吐司卷"
        title2 = "芋泥蛋皮吐司卷 厂家直销"
        similarity = service.calculate_similarity(title1, title2)
        assert similarity >= 50.0

    def test_low_similarity(self, service):
        """Test low similarity between different titles."""
        title1 = "芋泥蛋皮吐司卷"
        title2 = "手机壳iPhone15"
        similarity = service.calculate_similarity(title1, title2)
        assert similarity < 30.0

    def test_exact_match(self, service):
        """Test exact match."""
        title = "芋泥蛋皮吐司卷"
        similarity = service.calculate_similarity(title, title)
        assert similarity == 100.0

    def test_empty_titles(self, service):
        """Test with empty titles."""
        assert service.calculate_similarity("", "test") == 0.0
        assert service.calculate_similarity("test", "") == 0.0
        assert service.calculate_similarity("", "") == 0.0


# ── Profit Calculation Tests ─────────────────────────────────


class TestProfitCalculation:
    """Test profit calculation."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_profit_calculation_basic(self, service):
        """Test basic profit calculation."""
        # 售价69, 成本18 -> 利润率73.9%
        result = service.calculate_profit(sell_price=69.0, cost_price=18.0)
        assert result["estimated_profit"] == 51.0
        assert result["profit_margin"] == 73.9

    def test_profit_calculation_high_margin(self, service):
        """Test high margin calculation."""
        # 售价100, 成本20 -> 利润率80%
        result = service.calculate_profit(sell_price=100.0, cost_price=20.0)
        assert result["estimated_profit"] == 80.0
        assert result["profit_margin"] == 80.0

    def test_profit_calculation_low_margin(self, service):
        """Test low margin calculation."""
        # 售价100, 成本90 -> 利润率10%
        result = service.calculate_profit(sell_price=100.0, cost_price=90.0)
        assert result["estimated_profit"] == 10.0
        assert result["profit_margin"] == 10.0

    def test_profit_calculation_invalid_prices(self, service):
        """Test with invalid prices."""
        result = service.calculate_profit(sell_price=0.0, cost_price=18.0)
        assert result["estimated_profit"] == 0.0
        assert result["profit_margin"] == 0.0

        result = service.calculate_profit(sell_price=69.0, cost_price=0.0)
        assert result["estimated_profit"] == 0.0
        assert result["profit_margin"] == 0.0


# ── Match Product Tests ──────────────────────────────────────


class TestMatchProduct:
    """Test product matching."""

    @pytest.fixture
    def service(self):
        """Create SupplierMatchingService."""
        return SupplierMatchingService()

    def test_match_product_success(self, service):
        """Test successful product matching."""
        product = Product(
            id=1,
            name="芋泥味蛋皮吐司卷",
            platform="taobao",
            shop="某旗舰店",
            price=69.0,
        )

        supplier_products = [
            {
                "title": "芋泥蛋皮吐司卷 厂家直销 批发",
                "url": "https://detail.1688.com/offer/123.html",
                "price": 18.0,
            },
            {
                "title": "肉松面包 工厂货源",
                "url": "https://detail.1688.com/offer/456.html",
                "price": 15.0,
            },
        ]

        result = service.match_product(product, supplier_products)

        assert result is not None
        assert "芋泥" in result["supplier_title"]
        assert result["supplier_price"] == 18.0
        assert result["similarity_score"] > 0
        assert result["estimated_profit"] > 0
        assert result["profit_margin"] > 0

    def test_match_product_no_match(self, service):
        """Test when no match is found."""
        product = Product(
            id=1,
            name="芋泥味蛋皮吐司卷",
            platform="taobao",
            shop="某店铺",
            price=69.0,
        )

        supplier_products = [
            {
                "title": "手机壳 iPhone15 透明",
                "url": "https://detail.1688.com/offer/789.html",
                "price": 5.0,
            },
        ]

        result = service.match_product(product, supplier_products)
        # Should return None because similarity is too low
        assert result is None

    def test_match_product_empty_suppliers(self, service):
        """Test with empty supplier list."""
        product = Product(
            id=1,
            name="芋泥味蛋皮吐司卷",
            platform="taobao",
            price=69.0,
        )

        result = service.match_product(product, [])
        assert result is None

    def test_create_match_record(self, service):
        """Test creating a match record."""
        product = Product(id=1, name="测试商品", price=69.0)

        match_data = {
            "supplier_title": "供应商商品",
            "supplier_url": "https://1688.com/xxx",
            "supplier_price": 18.0,
            "similarity_score": 85.0,
            "estimated_profit": 51.0,
            "profit_margin": 73.9,
        }

        record = service.create_match_record(product, match_data)

        assert isinstance(record, SupplierMatch)
        assert record.product_id == 1
        assert record.supplier_title == "供应商商品"
        assert record.profit_margin == 73.9


# ── AlibabaSearchClient Tests ────────────────────────────────


class TestAlibabaSearchClient:
    """Test AlibabaSearchClient."""

    @pytest.mark.asyncio
    async def test_mock_search(self):
        """Test mock search mode."""
        client = AlibabaSearchClient(use_mock=True)
        results = await client.search_products("芋泥蛋皮吐司卷")

        assert len(results) > 0
        assert "title" in results[0]
        assert "url" in results[0]
        assert "price" in results[0]

    @pytest.mark.asyncio
    async def test_no_crawler_returns_empty(self):
        """Test with no crawler configured."""
        client = AlibabaSearchClient()
        results = await client.search_products("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_real_search_with_mock_crawler(self):
        """Test real search with mock crawler."""
        mock_crawler = MagicMock()
        mock_crawler.search_suppliers = AsyncMock(return_value=[])

        client = AlibabaSearchClient(crawler=mock_crawler)
        results = await client.search_products("test")

        assert results == []


# ── Integration Tests ────────────────────────────────────────


class TestTaobaoCrawlerMatching:
    """Test TaobaoCrawler matching integration."""

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
    async def test_match_new_products_empty(self, crawler):
        """Test matching when no new products."""
        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=[])

        mock_service = MagicMock()
        mock_client = AsyncMock()

        result = await crawler.match_new_products_with_suppliers(
            mock_repo, mock_service, mock_client
        )

        assert result["total"] == 0
        assert result["matched_count"] == 0

    @pytest.mark.asyncio
    async def test_match_new_products_success(self, crawler):
        """Test successful matching flow."""
        from datetime import datetime

        mock_products = [
            Product(
                id=1,
                name="芋泥味蛋皮吐司卷",
                platform="taobao",
                shop="某旗舰店",
                price=69.0,
                first_seen_time=datetime.now(),
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.find_new_products = AsyncMock(return_value=mock_products)
        mock_repo._session = AsyncMock()
        mock_repo._session.add_all = MagicMock()

        mock_service = MagicMock()
        mock_service.clean_title.return_value = "芋泥蛋皮吐司卷"
        mock_service.generate_search_keyword.return_value = "芋泥蛋皮吐司卷"
        mock_service.match_product.return_value = {
            "supplier_title": "芋泥蛋皮吐司卷 厂家直销",
            "supplier_url": "https://1688.com/xxx",
            "supplier_price": 18.0,
            "similarity_score": 85.0,
            "estimated_profit": 51.0,
            "profit_margin": 73.9,
        }
        mock_service.create_match_record.return_value = SupplierMatch(
            product_id=1,
            supplier_title="芋泥蛋皮吐司卷 厂家直销",
            supplier_price=18.0,
            similarity_score=85.0,
            estimated_profit=51.0,
            profit_margin=73.9,
        )

        mock_client = AsyncMock()
        mock_client.search_products.return_value = [
            {"title": "芋泥蛋皮吐司卷 厂家直销", "url": "https://1688.com/xxx", "price": 18.0},
        ]

        result = await crawler.match_new_products_with_suppliers(
            mock_repo, mock_service, mock_client
        )

        assert result["total"] == 1
        assert result["matched_count"] == 1


# ── Example Match Case ───────────────────────────────────────


class TestExampleMatchCase:
    """Test a complete example match case."""

    def test_full_example(self):
        """Test complete example: 三只松鼠芋泥味蛋皮吐司卷.

        淘宝商品: 三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点
        售价: 69元

        1688供应商: 芋泥蛋皮吐司卷 厂家直销 批发
        成本: 18元

        预期结果:
        - 利润率: 73.9%
        - 预估利润: 51元
        """
        service = SupplierMatchingService()

        # Step 1: Clean title
        original_title = "三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点"
        cleaned = service.clean_title(original_title)
        assert "三只松鼠" not in cleaned

        # Step 2: Generate keyword
        keyword = service.generate_search_keyword(cleaned)
        assert len(keyword) > 0

        # Step 3: Simulate supplier search results (use similar title for high similarity)
        supplier_products = [
            {
                "title": "芋泥蛋皮吐司卷肉松夹心面包 厂家直销",
                "url": "https://detail.1688.com/offer/mock_123.html",
                "price": 18.0,
            },
        ]

        # Step 4: Create product
        product = Product(
            id=1,
            name=original_title,
            platform="taobao",
            shop="三只松鼠旗舰店",
            price=69.0,
        )

        # Step 5: Match product
        result = service.match_product(product, supplier_products)

        assert result is not None
        assert result["supplier_price"] == 18.0
        assert result["estimated_profit"] == 51.0
        assert result["profit_margin"] == 73.9
        assert result["similarity_score"] > 50.0

        # Step 6: Create match record
        record = service.create_match_record(product, result)
        assert isinstance(record, SupplierMatch)
        assert record.product_id == 1
        assert record.profit_margin == 73.9
