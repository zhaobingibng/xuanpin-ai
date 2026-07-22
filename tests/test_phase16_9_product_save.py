"""Tests for Phase 16.9 Task 2: Product data saving and new product detection."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.product import Product
from app.database.product_repository import ProductRepository


# ── Product Model Tests ──────────────────────────────────────


class TestProductModel:
    """Test Product model enhancements."""

    def test_create_product(self):
        """Test creating a product with new fields."""
        now = datetime.now()
        product = Product(
            name="测试商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=123",
            price=99.9,
            first_seen_time=now,
            last_seen_time=now,
        )
        assert product.name == "测试商品"
        assert product.first_seen_time == now
        assert product.last_seen_time == now

    def test_product_has_first_seen_time(self):
        """Test product has first_seen_time field."""
        product = Product(
            name="测试商品",
            platform="taobao",
            shop="测试店铺",
        )
        assert hasattr(product, "first_seen_time")

    def test_product_has_last_seen_time(self):
        """Test product has last_seen_time field."""
        product = Product(
            name="测试商品",
            platform="taobao",
            shop="测试店铺",
        )
        assert hasattr(product, "last_seen_time")


# ── ProductRepository Tests ──────────────────────────────────


class TestProductRepository:
    """Test ProductRepository new methods."""

    @pytest.fixture
    def session(self):
        """Create mock async session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session):
        """Create ProductRepository with mock session."""
        return ProductRepository(session)

    async def test_save_product_new(self, repo, session):
        """Test saving a new product."""
        # Mock get_product_by_url to return None (new product)
        repo.get_product_by_url = AsyncMock(return_value=None)

        product, is_new = await repo.save_product(
            name="新商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=123",
            price=99.9,
        )

        assert is_new is True
        assert product.name == "新商品"
        assert product.first_seen_time is not None
        assert product.last_seen_time is not None
        assert product.lifecycle_stage == "NEW"
        session.add.assert_called_once()

    async def test_save_product_existing(self, repo, session):
        """Test saving an existing product updates last_seen_time."""
        old_time = datetime(2026, 1, 1)
        existing_product = Product(
            id=1,
            name="已存在商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=123",
            first_seen_time=old_time,
            last_seen_time=old_time,
        )

        # Mock get_product_by_url to return existing product
        repo.get_product_by_url = AsyncMock(return_value=existing_product)

        product, is_new = await repo.save_product(
            name="已存在商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=123",
            price=109.9,
        )

        assert is_new is False
        # last_seen_time should be updated to now (after old_time)
        assert product.last_seen_time > old_time
        assert product.price == 109.9

    async def test_get_product_by_url(self, repo, session):
        """Test getting product by URL."""
        mock_product = Product(
            id=1,
            name="测试商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=123",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_product
        session.execute = AsyncMock(return_value=mock_result)

        product = await repo.get_product_by_url("https://item.taobao.com/item.htm?id=123")
        assert product is not None
        assert product.url == "https://item.taobao.com/item.htm?id=123"

    async def test_get_product_by_url_not_found(self, repo, session):
        """Test getting product by URL when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        product = await repo.get_product_by_url("https://nonexistent.com")
        assert product is None

    async def test_get_product_by_url_empty(self, repo):
        """Test getting product by empty URL."""
        product = await repo.get_product_by_url("")
        assert product is None

        product = await repo.get_product_by_url(None)
        assert product is None

    async def test_get_recent_products(self, repo, session):
        """Test getting recent products."""
        mock_products = [
            Product(
                id=1,
                name="商品1",
                platform="taobao",
                shop="店铺1",
                last_seen_time=datetime.now(),
            ),
            Product(
                id=2,
                name="商品2",
                platform="taobao",
                shop="店铺2",
                last_seen_time=datetime.now(),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_products
        session.execute = AsyncMock(return_value=mock_result)

        products = await repo.get_recent_products(days=7)
        assert len(products) == 2

    async def test_find_new_products(self, repo, session):
        """Test finding new products."""
        mock_products = [
            Product(
                id=1,
                name="新品1",
                platform="taobao",
                shop="店铺1",
                lifecycle_stage="NEW",
                first_seen_time=datetime.now(),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_products
        session.execute = AsyncMock(return_value=mock_result)

        products = await repo.find_new_products()
        assert len(products) == 1
        assert products[0].lifecycle_stage == "NEW"


# ── TaobaoCrawler Integration Tests ──────────────────────────


class TestTaobaoCrawlerProductSave:
    """Test TaobaoCrawler product saving integration."""

    @pytest.fixture
    def crawler(self):
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)

            from app.crawler.taobao import TaobaoCrawler
            return TaobaoCrawler()

    async def test_save_crawled_products_empty(self, crawler):
        """Test saving empty product list."""
        mock_repo = AsyncMock()

        result = await crawler.save_crawled_products([], mock_repo)

        assert result["total"] == 0
        assert result["new_count"] == 0
        assert result["updated_count"] == 0

    async def test_save_crawled_products_new(self, crawler):
        """Test saving new products."""
        from app.crawler.models.schemas import RawProduct

        raw_products = [
            RawProduct(
                name="新商品1",
                platform="taobao",
                shop="测试店铺",
                url="https://item.taobao.com/item.htm?id=1",
                price=99.9,
            ),
            RawProduct(
                name="新商品2",
                platform="taobao",
                shop="测试店铺",
                url="https://item.taobao.com/item.htm?id=2",
                price=199.9,
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.save_product = AsyncMock(side_effect=[
            (MagicMock(), True),   # First product is new
            (MagicMock(), True),   # Second product is new
        ])
        mock_repo._session = AsyncMock()

        result = await crawler.save_crawled_products(raw_products, mock_repo)

        assert result["total"] == 2
        assert result["new_count"] == 2
        assert result["updated_count"] == 0

    async def test_save_crawled_products_mixed(self, crawler):
        """Test saving mix of new and existing products."""
        from app.crawler.models.schemas import RawProduct

        raw_products = [
            RawProduct(
                name="新商品",
                platform="taobao",
                shop="测试店铺",
                url="https://item.taobao.com/item.htm?id=1",
                price=99.9,
            ),
            RawProduct(
                name="已存在商品",
                platform="taobao",
                shop="测试店铺",
                url="https://item.taobao.com/item.htm?id=2",
                price=199.9,
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.save_product = AsyncMock(side_effect=[
            (MagicMock(), True),    # First is new
            (MagicMock(), False),   # Second is existing
        ])
        mock_repo._session = AsyncMock()

        result = await crawler.save_crawled_products(raw_products, mock_repo)

        assert result["total"] == 2
        assert result["new_count"] == 1
        assert result["updated_count"] == 1


# ── New Product Detection Logic Tests ────────────────────────


class TestNewProductDetection:
    """Test new product detection logic."""

    @pytest.fixture
    def session(self):
        """Create mock async session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session):
        """Create ProductRepository with mock session."""
        return ProductRepository(session)

    async def test_new_product_url_not_exists(self, repo, session):
        """Test: if product_url doesn't exist -> mark as NEW."""
        repo.get_product_by_url = AsyncMock(return_value=None)

        product, is_new = await repo.save_product(
            name="全新商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=new",
            price=99.9,
        )

        assert is_new is True
        assert product.lifecycle_stage == "NEW"
        assert product.first_seen_time is not None

    async def test_existing_product_url_exists(self, repo, session):
        """Test: if product_url exists -> update last_seen_time."""
        old_time = datetime(2026, 1, 1)
        existing = Product(
            id=1,
            name="已存在商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=existing",
            first_seen_time=old_time,
            last_seen_time=old_time,
            lifecycle_stage="ACTIVE",
        )

        repo.get_product_by_url = AsyncMock(return_value=existing)

        product, is_new = await repo.save_product(
            name="已存在商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=existing",
            price=109.9,
        )

        assert is_new is False
        assert product.last_seen_time > old_time
        assert product.lifecycle_stage == "ACTIVE"  # Stage unchanged

    async def test_duplicate_product_same_url(self, repo, session):
        """Test: duplicate products with same URL are handled."""
        existing = Product(
            id=1,
            name="商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=dup",
            first_seen_time=datetime.now(),
            last_seen_time=datetime.now(),
        )

        repo.get_product_by_url = AsyncMock(return_value=existing)

        # First save (simulated)
        _, is_new_1 = await repo.save_product(
            name="商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=dup",
            price=99.9,
        )

        # Second save (duplicate)
        _, is_new_2 = await repo.save_product(
            name="商品",
            platform="taobao",
            shop="测试店铺",
            url="https://item.taobao.com/item.htm?id=dup",
            price=99.9,
        )

        # Both should return is_new=False after first save
        assert is_new_2 is False
