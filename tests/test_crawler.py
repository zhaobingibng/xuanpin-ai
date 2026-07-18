"""Tests for crawler base utilities, data models, and manager."""

import pytest

from app.crawler.base import BaseCrawler
from app.crawler.models.schemas import RawProduct
from app.crawler.manager import CrawlerManager


# ── RawProduct ────────────────────────────────────────────────


class TestRawProduct:
    """Test the RawProduct dataclass."""

    def test_basic_creation(self):
        p = RawProduct(name="测试商品", platform="xiaohongshu", shop="测试店铺", price=99.9)
        assert p.name == "测试商品"
        assert p.platform == "xiaohongshu"
        assert p.shop == "测试店铺"
        assert p.price == 99.9
        assert p.viewers == 0
        assert p.sales_24h == 0
        assert p.image is None
        assert p.url is None

    def test_full_creation(self):
        p = RawProduct(
            name="高级面霜",
            platform="douyin",
            shop="美妆旗舰店",
            price=199.0,
            viewers=5000,
            sales_24h=320,
            image="https://img.example.com/product.jpg",
            url="https://example.com/product/123",
        )
        assert p.viewers == 5000
        assert p.sales_24h == 320
        assert p.image is not None
        assert p.url is not None

    def test_to_db_kwargs(self):
        p = RawProduct(
            name="防晒霜SPF50",
            platform="kuaishou",
            shop="护肤专营店",
            price=89.5,
            viewers=1200,
            sales_24h=45,
            image="https://img.example.com/sunscreen.jpg",
            url="https://example.com/product/456",
        )
        kwargs = p.to_db_kwargs()

        # url and crawled_at should NOT be in db kwargs
        assert "url" not in kwargs
        assert "crawled_at" not in kwargs

        # All product fields should be present
        assert kwargs["name"] == "防晒霜SPF50"
        assert kwargs["platform"] == "kuaishou"
        assert kwargs["shop"] == "护肤专营店"
        assert kwargs["price"] == 89.5
        assert kwargs["viewers"] == 1200
        assert kwargs["sales_24h"] == 45
        assert kwargs["image"] == "https://img.example.com/sunscreen.jpg"

    def test_to_db_kwargs_minimal(self):
        p = RawProduct(name="简约商品", platform="xiaohongshu", shop="简店", price=10.0)
        kwargs = p.to_db_kwargs()
        assert kwargs["viewers"] == 0
        assert kwargs["sales_24h"] == 0
        assert kwargs["image"] is None


# ── BaseCrawler.parse_count ───────────────────────────────────


class TestParseCount:
    """Test the static parse_count utility."""

    def test_plain_integer(self):
        assert BaseCrawler.parse_count("1234") == 1234

    def test_wan_suffix(self):
        assert BaseCrawler.parse_count("1.2万") == 12000

    def test_wan_integer(self):
        assert BaseCrawler.parse_count("3万") == 30000

    def test_yi_suffix(self):
        assert BaseCrawler.parse_count("1.5亿") == 150_000_000

    def test_empty_string(self):
        assert BaseCrawler.parse_count("") == 0

    def test_whitespace(self):
        assert BaseCrawler.parse_count("   ") == 0

    def test_no_digits(self):
        assert BaseCrawler.parse_count("暂无数据") == 0

    def test_mixed_text_with_number(self):
        assert BaseCrawler.parse_count("已售500") == 500

    def test_mixed_text_with_wan(self):
        assert BaseCrawler.parse_count("浏览2.5万次") == 25000

    def test_decimal_wan(self):
        assert BaseCrawler.parse_count("12.34万") == 123400

    def test_leading_trailing_spaces(self):
        assert BaseCrawler.parse_count("  100  ") == 100


# ── CrawlerManager ────────────────────────────────────────────


class _StubCrawler(BaseCrawler):
    """Minimal concrete crawler for testing."""

    def __init__(self, platform: str = "test") -> None:
        self.PLATFORM = platform
        self.BASE_URL = "https://example.com"
        # Skip super().__init__() to avoid settings/playwright dependency
        self._playwright = None
        self._browser = None

    async def crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        return [
            RawProduct(
                name=f"{keyword}-商品1",
                platform=self.PLATFORM,
                shop="测试店铺",
                price=99.0,
            ),
            RawProduct(
                name=f"{keyword}-商品2",
                platform=self.PLATFORM,
                shop="测试店铺",
                price=199.0,
            ),
        ]

    async def _parse_product(self, element):
        return None


class TestCrawlerManager:
    """Test CrawlerManager registration and execution."""

    def test_register(self):
        manager = CrawlerManager()
        crawler = _StubCrawler("test_platform")
        manager.register(crawler)
        assert "test_platform" in manager.platforms
        assert len(manager) == 1

    def test_register_multiple(self):
        manager = CrawlerManager()
        manager.register(_StubCrawler("platform_a"))
        manager.register(_StubCrawler("platform_b"))
        manager.register(_StubCrawler("platform_c"))
        assert len(manager) == 3
        assert set(manager.platforms) == {"platform_a", "platform_b", "platform_c"}

    def test_register_overwrites(self):
        manager = CrawlerManager()
        manager.register(_StubCrawler("dup"))
        manager.register(_StubCrawler("dup"))
        assert len(manager) == 1

    @pytest.mark.asyncio
    async def test_crawl_single(self):
        manager = CrawlerManager()
        manager.register(_StubCrawler("test"))
        products = await manager.crawl("test", keyword="面膜")
        assert len(products) == 2
        assert products[0].name == "面膜-商品1"
        assert products[1].name == "面膜-商品2"
        assert all(p.platform == "test" for p in products)

    @pytest.mark.asyncio
    async def test_crawl_unknown_platform(self):
        manager = CrawlerManager()
        products = await manager.crawl("nonexistent", keyword="面膜")
        assert products == []

    @pytest.mark.asyncio
    async def test_crawl_all(self):
        manager = CrawlerManager()
        manager.register(_StubCrawler("xhs"))
        manager.register(_StubCrawler("dy"))
        results = await manager.crawl_all(keyword="精华液")
        assert "xhs" in results
        assert "dy" in results
        assert len(results["xhs"]) == 2
        assert len(results["dy"]) == 2

    @pytest.mark.asyncio
    async def test_crawl_all_empty_manager(self):
        manager = CrawlerManager()
        results = await manager.crawl_all(keyword="面膜")
        assert results == {}

    @pytest.mark.asyncio
    async def test_save_to_db(self):
        """Test save_to_db with a mock session."""
        from unittest.mock import AsyncMock

        manager = CrawlerManager()
        products = [
            RawProduct(name="商品A", platform="test", shop="店A", price=10.0),
            RawProduct(name="商品B", platform="test", shop="店B", price=20.0),
        ]
        mock_session = AsyncMock()
        count = await manager.save_to_db(products, mock_session)
        assert count == 2

    @pytest.mark.asyncio
    async def test_save_to_db_partial_failure(self):
        """Test save_to_db when one product fails."""
        from unittest.mock import AsyncMock, patch

        manager = CrawlerManager()
        products = [
            RawProduct(name="好商品", platform="test", shop="店A", price=10.0),
            RawProduct(name="坏商品", platform="test", shop="店B", price=20.0),
        ]
        mock_session = AsyncMock()

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Simulated DB error")
            return AsyncMock()

        # Patch at source since manager.py uses a lazy (in-function) import
        with patch("app.services.product_service.ProductService") as mock_ps:
            mock_ps.return_value.create = mock_create
            count = await manager.save_to_db(products, mock_session)
            assert count == 1
