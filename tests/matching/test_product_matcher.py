"""Tests for Phase 27: ProductMatcher."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.matching.product_matcher import ProductMatcher
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


async def _insert_products(session: AsyncSession) -> None:
    """Insert test supplier products."""
    products = [
        SupplierProductDB(
            offer_id="p1",
            title="三只松鼠坚果礼盒装2024新款",
            price=89.9,
            shop_name="三只松鼠旗舰店",
            url="https://detail.1688.com/offer/p1.html",
            image="https://img.alicdn.com/p1.jpg",
        ),
        SupplierProductDB(
            offer_id="p2",
            title="海苔卷零食大礼包即食脆",
            price=29.9,
            shop_name="海味零食铺",
            url="https://detail.1688.com/offer/p2.html",
            image="https://img.alicdn.com/p2.jpg",
        ),
        SupplierProductDB(
            offer_id="p3",
            title="无线蓝牙耳机降噪运动款",
            price=59.0,
            shop_name="数码科技店",
            url="https://detail.1688.com/offer/p3.html",
            image="https://img.alicdn.com/p3.jpg",
        ),
        SupplierProductDB(
            offer_id="p4",
            title="坚果零食大礼包混合装",
            price=49.9,
            shop_name="零食批发中心",
            url="https://detail.1688.com/offer/p4.html",
            image="https://img.alicdn.com/p4.jpg",
        ),
    ]
    for p in products:
        session.add(p)
    await session.flush()


# ── Tests ────────────────────────────────────────────────────

class TestProductMatcher:
    """Test ProductMatcher.match_product method."""

    @pytest.mark.asyncio
    async def test_match_returns_results(self, session):
        """Should return matching results."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("三只松鼠坚果礼盒")

        assert len(results) > 0
        # First result should be the most relevant
        assert results[0]["offer_id"] == "p1"
        assert results[0]["similarity_score"] > 0.3

    @pytest.mark.asyncio
    async def test_match_result_fields(self, session):
        """Results should contain all required fields including new fusion fields."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("坚果礼盒")

        assert len(results) > 0
        result = results[0]
        # Old fields
        assert "supplier_product_id" in result
        assert "similarity_score" in result
        assert "title" in result
        assert "price" in result
        assert "url" in result
        assert "offer_id" in result
        assert "shop_name" in result
        assert "image" in result
        # New fusion fields (Phase 28)
        assert "text_score" in result
        assert "feature_score" in result
        assert "final_score" in result
        assert result["final_score"] == pytest.approx(result["similarity_score"], abs=0.001)

    @pytest.mark.asyncio
    async def test_match_synonym_products(self, session):
        """Should match synonym/similar products."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("坚果零食混合装")
        
        # Should match p1 and p4 (both contain 坚果)
        offer_ids = [r["offer_id"] for r in results]
        assert "p1" in offer_ids or "p4" in offer_ids

    @pytest.mark.asyncio
    async def test_match_different_products(self, session):
        """Different products should have low scores."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("蓝牙耳机降噪")
        
        # Best match should be p3 (蓝牙耳机)
        if results:
            assert results[0]["offer_id"] == "p3"

    @pytest.mark.asyncio
    async def test_match_empty_title(self, session):
        """Empty title should return empty list."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("")
        assert results == []

    @pytest.mark.asyncio
    async def test_match_whitespace_title(self, session):
        """Whitespace-only title should return empty list."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_match_top_k_limit(self, session):
        """top_k should limit results."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("零食", top_k=2)
        
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_match_top_k_default(self, session):
        """Default top_k should be 10."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        # Insert more products to exceed default top_k
        for i in range(15):
            session.add(SupplierProductDB(
                offer_id=f"extra_{i}",
                title=f"零食商品{i}",
                price=10.0,
            ))
        await session.flush()
        
        results = await matcher.match_product("零食")
        
        assert len(results) <= 10

    @pytest.mark.asyncio
    async def test_match_empty_database(self, session):
        """Empty database should return empty list."""
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("坚果礼盒")
        assert results == []

    @pytest.mark.asyncio
    async def test_match_score_ordering(self, session):
        """Results should be ordered by final_score descending."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("坚果礼盒装")
        
        scores = [r["final_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_match_zero_score_excluded(self, session):
        """Results with score 0 should be excluded."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("坚果礼盒")
        
        for r in results:
            assert r["final_score"] > 0

    @pytest.mark.asyncio
    async def test_fusion_scores_consistent(self, session):
        """fusion final_score should equal text_score*0.6 + feature_score*0.4."""
        await _insert_products(session)
        matcher = ProductMatcher(session)
        
        results = await matcher.match_product("坚果礼盒")
        
        for r in results:
            expected = r["text_score"] * 0.6 + r["feature_score"] * 0.4
            assert r["final_score"] == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_same_category_in_results(self, session):
        """Products with same category should appear in results with significant score."""
        # Add a product with same category (食品)
        session.add(SupplierProductDB(
            offer_id="p5",
            title="坚果零食混合大礼包",
            price=69.9,
            shop_name="坚果优选",
            url="https://detail.1688.com/offer/p5.html",
        ))
        await session.flush()
        
        matcher = ProductMatcher(session)
        results = await matcher.match_product("三只松鼠坚果礼盒")
        
        # p5 (食品, 坚果零食) should definitely appear
        offer_ids = [r["offer_id"] for r in results]
        assert "p5" in offer_ids, "Same-category product should appear in results"
        # p5 should have a non-zero feature_score
        for r in results:
            if r["offer_id"] == "p5":
                assert r["feature_score"] > 0, "Same-category product should have feature boost"
                assert r["final_score"] > 0.2, "Same-category product should have reasonable score"
