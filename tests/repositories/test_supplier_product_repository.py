"""Tests for Phase 26: SupplierProductRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crawler.event_parser import ParsedProduct
from app.database.base import Base
from app.repositories.supplier_product_repository import SupplierProductRepository
from app.models.supplier_product import SupplierProductDB

# ensure models registered
import app.models  # noqa: F401


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
async def session():
    """Create async in-memory session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def repo(session):
    """Create repository instance."""
    return SupplierProductRepository(session)


def _make_parsed_product(**overrides) -> ParsedProduct:
    """Create a ParsedProduct with defaults."""
    defaults = {
        "title": "测试商品",
        "price": 29.9,
        "sales": 100,
        "shop_name": "测试供应商",
        "offer_id": "test_001",
        "url": "https://detail.1688.com/offer/test_001.html",
        "image": "https://cbu01.alicdn.com/test.jpg",
        "source": "1688",
    }
    defaults.update(overrides)
    return ParsedProduct(**defaults)


# ── Test: save_products ──────────────────────────────────────

class TestSaveProducts:
    """Test save_products method."""

    @pytest.mark.asyncio
    async def test_save_single_product(self, repo, session):
        """Test saving a single product."""
        product = _make_parsed_product()
        saved = await repo.save_products([product])

        assert len(saved) == 1
        assert saved[0].offer_id == "test_001"
        assert saved[0].title == "测试商品"
        assert saved[0].price == 29.9

    @pytest.mark.asyncio
    async def test_save_multiple_products(self, repo):
        """Test saving multiple products."""
        products = [
            _make_parsed_product(offer_id="p1", title="商品1"),
            _make_parsed_product(offer_id="p2", title="商品2"),
            _make_parsed_product(offer_id="p3", title="商品3"),
        ]
        saved = await repo.save_products(products)

        assert len(saved) == 3

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, repo):
        """Test that saving with same offer_id updates the record."""
        # First save
        p1 = _make_parsed_product(offer_id="update_001", title="原标题", price=10.0)
        await repo.save_products([p1])

        # Second save with same offer_id but different data
        p2 = _make_parsed_product(offer_id="update_001", title="新标题", price=20.0)
        saved = await repo.save_products([p2])

        assert len(saved) == 1
        assert saved[0].title == "新标题"
        assert saved[0].price == 20.0

    @pytest.mark.asyncio
    async def test_save_skips_empty_offer_id(self, repo):
        """Test that products without offer_id are skipped."""
        product = _make_parsed_product(offer_id="")
        saved = await repo.save_products([product])

        assert len(saved) == 0

    @pytest.mark.asyncio
    async def test_save_empty_list(self, repo):
        """Test saving empty list."""
        saved = await repo.save_products([])
        assert len(saved) == 0


# ── Test: get_by_offer_id ────────────────────────────────────

class TestGetByOfferId:
    """Test get_by_offer_id method."""

    @pytest.mark.asyncio
    async def test_get_existing(self, repo):
        """Test getting an existing product."""
        product = _make_parsed_product(offer_id="get_001")
        await repo.save_products([product])

        result = await repo.get_by_offer_id("get_001")
        assert result is not None
        assert result.offer_id == "get_001"
        assert result.title == "测试商品"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        """Test getting a non-existent product."""
        result = await repo.get_by_offer_id("nonexistent")
        assert result is None


# ── Test: search_by_keyword ──────────────────────────────────

class TestSearchByKeyword:
    """Test search_by_keyword method."""

    @pytest.mark.asyncio
    async def test_search_matching(self, repo):
        """Test search with matching keyword."""
        products = [
            _make_parsed_product(offer_id="s1", title="海苔卷零食大礼包"),
            _make_parsed_product(offer_id="s2", title="海苔卷即食脆"),
            _make_parsed_product(offer_id="s3", title="坚果礼盒装"),
        ]
        await repo.save_products(products)

        results = await repo.search_by_keyword("海苔卷")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_no_match(self, repo):
        """Test search with no matching keyword."""
        product = _make_parsed_product(offer_id="nm1", title="海苔卷零食")
        await repo.save_products([product])

        results = await repo.search_by_keyword("不存在的关键词")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_empty_db(self, repo):
        """Test search on empty database."""
        results = await repo.search_by_keyword("海苔卷")
        assert len(results) == 0


# ── Test: get_all & count ────────────────────────────────────

class TestGetAllAndCount:
    """Test get_all and count methods."""

    @pytest.mark.asyncio
    async def test_get_all(self, repo):
        """Test getting all products."""
        products = [
            _make_parsed_product(offer_id="a1"),
            _make_parsed_product(offer_id="a2"),
        ]
        await repo.save_products(products)

        results = await repo.get_all()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_count(self, repo):
        """Test counting products."""
        products = [
            _make_parsed_product(offer_id="c1"),
            _make_parsed_product(offer_id="c2"),
            _make_parsed_product(offer_id="c3"),
        ]
        await repo.save_products(products)

        count = await repo.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_empty(self, repo):
        """Test counting on empty database."""
        count = await repo.count()
        assert count == 0


# ── Test: Integration with EventParser ───────────────────────

class TestEventParserIntegration:
    """Test integration with EventParser output."""

    @pytest.mark.asyncio
    async def test_save_parsed_products(self, repo):
        """Test saving products from EventParser."""
        from app.crawler.event_parser import EventParser

        parser = EventParser()
        events = [
            {
                "type": "offerV2",
                "detail": {
                    "response": {
                        "data": {
                            "offerList": [
                                {
                                    "offer": {
                                        "offerId": "parser_001",
                                        "title": "解析器测试商品",
                                        "priceInfo": {"price": "39.9"},
                                        "companyName": "解析器供应商",
                                    }
                                }
                            ]
                        }
                    }
                },
            }
        ]

        parsed = parser.parse_events(events)
        assert len(parsed) == 1

        saved = await repo.save_products(parsed)
        assert len(saved) == 1
        assert saved[0].offer_id == "parser_001"
        assert saved[0].title == "解析器测试商品"
        assert saved[0].price == 39.9
