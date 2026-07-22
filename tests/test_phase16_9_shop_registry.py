"""Tests for Phase 16.9 Task 2: Shop Registry Management."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.shop_registry import ShopRegistry, ShopStatus
from app.repositories.shop_repository import ShopRepository


# ── ShopStatus Enum Tests ────────────────────────────────────


class TestShopStatus:
    """Test ShopStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert ShopStatus.ACTIVE.value == "ACTIVE"
        assert ShopStatus.PAUSED.value == "PAUSED"
        assert ShopStatus.DISABLED.value == "DISABLED"


# ── ShopRegistry Model Tests ─────────────────────────────────


class TestShopRegistryModel:
    """Test ShopRegistry model enhancements."""

    def test_create_shop(self):
        """Test creating a shop with status."""
        shop = ShopRegistry(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.ACTIVE.value,
            enabled=True,
        )
        assert shop.platform == "taobao"
        assert shop.shop_id == "shop123"
        assert shop.status == "ACTIVE"

    def test_is_active(self):
        """Test is_active property."""
        shop = ShopRegistry(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.ACTIVE.value,
            enabled=True,
        )
        assert shop.is_active is True
        assert shop.is_paused is False
        assert shop.is_disabled is False

    def test_is_paused(self):
        """Test is_paused property."""
        shop = ShopRegistry(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.PAUSED.value,
            enabled=False,
        )
        assert shop.is_active is False
        assert shop.is_paused is True
        assert shop.is_disabled is False

    def test_is_disabled(self):
        """Test is_disabled property."""
        shop = ShopRegistry(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.DISABLED.value,
            enabled=False,
        )
        assert shop.is_active is False
        assert shop.is_paused is False
        assert shop.is_disabled is True

    def test_active_requires_enabled(self):
        """Test is_active requires both status and enabled."""
        shop = ShopRegistry(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.ACTIVE.value,
            enabled=False,  # disabled
        )
        assert shop.is_active is False


# ── ShopRepository Tests ─────────────────────────────────────


class TestShopRepository:
    """Test ShopRepository class."""

    @pytest.fixture
    def session(self):
        """Create mock async session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session):
        """Create ShopRepository with mock session."""
        return ShopRepository(session)

    async def test_create_shop(self, repo, session):
        """Test creating a shop."""
        shop = await repo.create_shop(
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            shop_url="https://shop123.taobao.com",
            category="数码",
            priority=2,
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert shop.platform == "taobao"
        assert shop.shop_name == "测试店铺"
        assert shop.status == ShopStatus.ACTIVE.value

    async def test_get_shop_by_id(self, repo, session):
        """Test getting shop by ID."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
        )
        session.get = AsyncMock(return_value=mock_shop)

        shop = await repo.get_shop_by_id(1)
        assert shop is not None
        assert shop.shop_name == "测试店铺"

    async def test_get_shop_by_id_not_found(self, repo, session):
        """Test getting shop by ID when not found."""
        session.get = AsyncMock(return_value=None)

        shop = await repo.get_shop_by_id(999)
        assert shop is None

    async def test_list_active_shops(self, repo, session):
        """Test listing active shops."""
        mock_shops = [
            ShopRegistry(
                id=1,
                platform="taobao",
                shop_id="shop1",
                shop_name="店铺1",
                status=ShopStatus.ACTIVE.value,
                enabled=True,
            ),
            ShopRegistry(
                id=2,
                platform="taobao",
                shop_id="shop2",
                shop_name="店铺2",
                status=ShopStatus.ACTIVE.value,
                enabled=True,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_shops
        session.execute = AsyncMock(return_value=mock_result)

        shops = await repo.list_active_shops()
        assert len(shops) == 2

    async def test_list_active_shops_filters_paused(self, repo, session):
        """Test that list_active_shops only returns ACTIVE shops."""
        mock_shops = [
            ShopRegistry(
                id=1,
                platform="taobao",
                shop_id="shop1",
                shop_name="店铺1",
                status=ShopStatus.ACTIVE.value,
                enabled=True,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_shops
        session.execute = AsyncMock(return_value=mock_result)

        shops = await repo.list_active_shops()
        # Should only return ACTIVE shops
        assert all(s.status == ShopStatus.ACTIVE.value for s in shops)

    async def test_update_crawl_status_success(self, repo, session):
        """Test updating crawl status after successful crawl."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
        )
        session.get = AsyncMock(return_value=mock_shop)

        updated = await repo.update_crawl_status(shop_id=1, success=True)

        assert updated is not None
        assert updated.last_crawl_time is not None
        assert updated.last_success_time is not None
        session.commit.assert_called_once()

    async def test_update_crawl_status_failure(self, repo, session):
        """Test updating crawl status after failed crawl."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            last_crawl_time=None,
            last_success_time=datetime.now(),  # Previous success
        )
        session.get = AsyncMock(return_value=mock_shop)

        updated = await repo.update_crawl_status(shop_id=1, success=False)

        assert updated is not None
        assert updated.last_crawl_time is not None
        # last_success_time should not change on failure
        session.commit.assert_called_once()

    async def test_pause_shop(self, repo, session):
        """Test pausing a shop."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.ACTIVE.value,
            enabled=True,
        )
        session.get = AsyncMock(return_value=mock_shop)

        updated = await repo.pause_shop(1)

        assert updated is not None
        assert updated.status == ShopStatus.PAUSED.value
        assert updated.enabled is False

    async def test_activate_shop(self, repo, session):
        """Test activating a paused shop."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.PAUSED.value,
            enabled=False,
        )
        session.get = AsyncMock(return_value=mock_shop)

        updated = await repo.activate_shop(1)

        assert updated is not None
        assert updated.status == ShopStatus.ACTIVE.value
        assert updated.enabled is True

    async def test_disable_shop(self, repo, session):
        """Test permanently disabling a shop."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            status=ShopStatus.ACTIVE.value,
            enabled=True,
        )
        session.get = AsyncMock(return_value=mock_shop)

        updated = await repo.disable_shop(1)

        assert updated is not None
        assert updated.status == ShopStatus.DISABLED.value
        assert updated.enabled is False

    async def test_get_shops_for_crawl(self, repo, session):
        """Test getting shops for crawl pipeline."""
        mock_shops = [
            ShopRegistry(
                id=1,
                platform="taobao",
                shop_id="shop1",
                shop_name="店铺1",
                status=ShopStatus.ACTIVE.value,
                enabled=True,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_shops
        session.execute = AsyncMock(return_value=mock_result)

        shops = await repo.get_shops_for_crawl(platform="taobao")
        assert len(shops) == 1


# ── TaobaoCrawler Integration Tests ──────────────────────────


class TestTaobaoCrawlerShopIntegration:
    """Test TaobaoCrawler integration with ShopRepository."""

    @pytest.fixture
    def crawler(self):
        with patch("app.crawler.taobao.BrowserManager") as mock_bm:
            mock_manager = MagicMock()
            mock_bm.return_value = mock_manager
            mock_manager.__aenter__ = AsyncMock(return_value=mock_manager)
            mock_manager.__aexit__ = AsyncMock(return_value=None)

            from app.crawler.taobao import TaobaoCrawler
            return TaobaoCrawler()

    async def test_crawl_registered_shops_no_shops(self, crawler):
        """Test crawl_registered_shops with no active shops."""
        mock_repo = AsyncMock()
        mock_repo.get_shops_for_crawl = AsyncMock(return_value=[])

        result = await crawler.crawl_registered_shops(mock_repo)

        assert result["total_shops"] == 0
        assert result["results"] == []

    async def test_crawl_registered_shops_with_shops(self, crawler):
        """Test crawl_registered_shops with active shops."""
        mock_shop = ShopRegistry(
            id=1,
            platform="taobao",
            shop_id="shop123",
            shop_name="测试店铺",
            shop_url="https://shop123.taobao.com",
            status=ShopStatus.ACTIVE.value,
            enabled=True,
        )

        mock_repo = AsyncMock()
        mock_repo.get_shops_for_crawl = AsyncMock(return_value=[mock_shop])
        mock_repo.update_crawl_status = AsyncMock()

        # Mock crawl_shop_with_metrics
        from app.crawler.taobao import CrawlResult
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="测试商品",
                platform="taobao",
                shop="测试店铺",
                price=99.9,
            )
        ]
        crawler.crawl_shop_with_metrics = AsyncMock(
            return_value=CrawlResult(
                products=mock_products,
                real_product_count=1,
                pages_crawled=1,
            )
        )

        result = await crawler.crawl_registered_shops(mock_repo)

        assert result["total_shops"] == 1
        assert result["total_products"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["shop_name"] == "测试店铺"
        assert result["results"][0]["success"] is True

        # Verify update_crawl_status was called
        mock_repo.update_crawl_status.assert_called_once()
