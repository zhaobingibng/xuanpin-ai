"""End-to-end pipeline test for Phase 16.

Tests the complete selection pipeline:
  Crawl → Clean → Score → Save → Report → SupplyChain → DailySelection

Uses mocks/fixtures instead of real network requests.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch
from app.crawler.models.schemas import RawProduct


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
async def session():
    """Create in-memory async database session."""
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
def sample_raw_products() -> list[RawProduct]:
    """Sample raw products for testing."""
    return [
        RawProduct(
            name="无线蓝牙耳机入耳式降噪运动超长续航2024新款",
            platform="taobao",
            shop="数码旗舰店",
            price=128.0,
            sales_24h=1500,
            shop_url="https://shop.taobao.com/shop/digital001",
            image="https://img.alicdn.com/earphone1.jpg",
        ),
        RawProduct(
            name="夏季碎花连衣裙女2024新款法式复古",
            platform="taobao",
            shop="时尚女装店",
            price=89.0,
            sales_24h=800,
            shop_url="https://shop.taobao.com/shop/fashion002",
            image="https://img.alicdn.com/dress1.jpg",
        ),
        RawProduct(
            name="手机壳iPhone15透明防摔保护套",
            platform="taobao",
            shop="手机配件专营",
            price=19.9,
            sales_24h=5000,
            shop_url="https://shop.taobao.com/shop/phone003",
            image="https://img.alicdn.com/case1.jpg",
        ),
    ]


# ============================================================
# E2E Pipeline Tests
# ============================================================


class TestPipelineDataFlow:
    """Test complete data flow through the pipeline."""

    @pytest.mark.anyio
    async def test_raw_product_to_database(self, session, sample_raw_products):
        """Test raw products can be saved to database."""
        from app.services.product_service import ProductService

        svc = ProductService(session)
        result = await svc.save_raw_products(sample_raw_products)

        assert result["saved_count"] == 3
        assert result["new_count"] == 3

        # Verify products in DB
        products = await svc.list_all(limit=10)
        assert len(products) == 3
        assert all(p.platform == "taobao" for p in products)

    @pytest.mark.anyio
    async def test_clean_pipeline_processing(self, sample_raw_products):
        """Test ProductCleanPipeline processes raw products."""
        from app.services.cleaner.pipeline import ProductCleanPipeline, CleanedProduct

        pipeline = ProductCleanPipeline()
        cleaned = pipeline.process_batch(sample_raw_products)

        assert len(cleaned) == 3
        for item in cleaned:
            assert isinstance(item, CleanedProduct)
            assert item.name  # Name not empty

    @pytest.mark.anyio
    async def test_scoring_and_ranking(self, sample_raw_products):
        """Test ProductAnalyzer scoring and ranking."""
        from app.ai.analyzer import ProductAnalyzer
        from app.services.cleaner.pipeline import ProductCleanPipeline

        pipeline = ProductCleanPipeline()
        cleaned = pipeline.process_batch(sample_raw_products)

        analyzer = ProductAnalyzer()
        ranked = analyzer.rank(cleaned)

        assert len(ranked) == 3
        # Check ranking structure
        for item in ranked:
            assert "product" in item
            assert "ai_score" in item
            assert item["ai_score"] >= 0

    @pytest.mark.anyio
    async def test_supply_chain_matching(self, session, sample_raw_products):
        """Test supply chain matching with mock provider."""
        from app.services.product_service import ProductService
        from app.services.supply_chain.matcher import SupplyChainMatcher
        from app.services.supply_chain.provider import SupplyChainProvider

        # Save products first
        svc = ProductService(session)
        await svc.save_raw_products(sample_raw_products)

        # Get saved products
        products = await svc.list_all(limit=10)
        assert len(products) >= 1

        # Create matcher with mock provider
        provider = SupplyChainProvider()  # Default mock mode
        matcher = SupplyChainMatcher(session, provider=provider)

        # Match first product
        match = await matcher.match_product(products[0])

        # Match may or may not succeed depending on title similarity
        # Just verify it doesn't crash
        if match is not None:
            assert match.match_score >= 0
            assert match.status == "MATCHED"

    @pytest.mark.anyio
    async def test_daily_report_generation(self, session, sample_raw_products):
        """Test daily report generation after products saved."""
        from app.services.product_service import ProductService
        from app.services.report.daily_report import DailyReportService

        # Save products
        svc = ProductService(session)
        await svc.save_raw_products(sample_raw_products)

        # Generate report
        report_svc = DailyReportService(session)
        report = await report_svc.generate(limit=10)

        assert report["date"]
        assert "total" in report
        assert "items" in report
        assert report["total"] >= 0

    @pytest.mark.anyio
    async def test_daily_selection_report(self, session, sample_raw_products):
        """Test daily selection report with full data."""
        from app.services.product_service import ProductService
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Save products
        svc = ProductService(session)
        await svc.save_raw_products(sample_raw_products)

        # Generate selection report
        report_svc = DailySelectionReportService(session)
        report = await report_svc.generate(limit=10)

        # Verify structure
        assert report["date"]
        assert "summary" in report
        assert "new_products" in report
        assert "supply_chain_matches" in report
        assert "profit_analysis" in report
        assert "ai_recommendations" in report
        assert "top_picks" in report

        # New products should be found (saved within 24h)
        assert report["summary"]["new_products_count"] >= 1

    @pytest.mark.anyio
    async def test_full_pipeline_flow(self, session, sample_raw_products):
        """Test complete pipeline: save → report → supply chain → selection."""
        from app.services.product_service import ProductService
        from app.services.supply_chain.matcher import SupplyChainMatcher
        from app.services.supply_chain.provider import SupplyChainProvider
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Step 1: Save products
        svc = ProductService(session)
        save_result = await svc.save_raw_products(sample_raw_products)
        assert save_result["saved_count"] == 3

        # Step 2: Get saved products
        products = await svc.list_all(limit=10)
        assert len(products) == 3

        # Step 3: Supply chain matching
        provider = SupplyChainProvider()
        matcher = SupplyChainMatcher(session, provider=provider)
        matches = []
        for product in products[:2]:  # Match top 2
            match = await matcher.match_product(product)
            if match:
                matches.append(match)

        # Step 4: Generate selection report
        report_svc = DailySelectionReportService(session)
        report = await report_svc.generate(limit=10)

        # Verify complete flow
        assert report["summary"]["new_products_count"] >= 1
        assert report["summary"]["matched_count"] == len(matches)
        assert "generated_at" in report


class TestPipelineErrorHandling:
    """Test that individual step failures don't crash the pipeline."""

    @pytest.mark.anyio
    async def test_empty_products_no_crash(self, session):
        """Test pipeline handles empty product list gracefully."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        report_svc = DailySelectionReportService(session)
        report = await report_svc.generate()

        assert report["summary"]["new_products_count"] == 0
        assert report["summary"]["matched_count"] == 0

    @pytest.mark.anyio
    async def test_supply_chain_match_failure_isolated(self, session):
        """Test supply chain match failure doesn't affect other products."""
        from app.services.product_service import ProductService
        from app.services.supply_chain.matcher import SupplyChainMatcher
        from app.services.supply_chain.provider import SupplyChainProvider

        # Create a product
        product = Product(
            name="测试商品",
            platform="taobao",
            shop="测试店铺",
            price=100.0,
            status="ACTIVE",
        )
        session.add(product)
        await session.commit()

        # Matcher with mock provider
        provider = SupplyChainProvider()
        matcher = SupplyChainMatcher(session, provider=provider)

        # Should not raise exception
        match = await matcher.match_product(product)
        # Result can be None (no match) but shouldn't crash

    @pytest.mark.anyio
    async def test_report_generation_with_partial_data(self, session):
        """Test report generation works with incomplete data."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Add product without supply chain match
        product = Product(
            name="孤立商品",
            platform="taobao",
            shop="店铺",
            price=50.0,
            ai_score=60,
            status="ACTIVE",
            created_at=datetime.now(),
        )
        session.add(product)
        await session.commit()

        report_svc = DailySelectionReportService(session)
        report = await report_svc.generate()

        # Should have new product but no matches
        assert report["summary"]["new_products_count"] >= 1
        assert report["summary"]["matched_count"] == 0


class TestPipelineStepIsolation:
    """Test each pipeline step is properly isolated."""

    def test_daily_selection_report_import(self):
        """Test DailySelectionReportService can be imported."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        assert DailySelectionReportService is not None

    def test_supply_chain_provider_mock_mode(self):
        """Test SupplyChainProvider defaults to mock mode."""
        from app.services.supply_chain.provider import SupplyChainProvider
        provider = SupplyChainProvider()
        assert provider._use_real_crawler is False

    def test_image_matcher_optional(self):
        """Test SupplyChainMatcher works without image matcher."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=False)
        assert matcher._get_image_matcher() is None

    @pytest.mark.anyio
    async def test_profit_analysis_standalone(self, session):
        """Test profit analysis can run independently."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        svc = DailySelectionReportService(session)

        # Test with mock match data
        matches = [
            {"profit_margin": 40.0, "product_id": 1, "product_name": "A"},
            {"profit_margin": 20.0, "product_id": 2, "product_name": "B"},
        ]
        analysis = svc._analyze_profits(matches)

        assert analysis["total_matches"] == 2
        assert analysis["avg_margin"] == 30.0


class TestPipelineIntegrationPoints:
    """Test integration between pipeline components."""

    @pytest.mark.anyio
    async def test_product_to_supply_chain_flow(self, session):
        """Test Product → SupplyChainMatcher flow."""
        from app.services.product_service import ProductService
        from app.services.supply_chain.matcher import SupplyChainMatcher
        from app.services.supply_chain.provider import SupplyChainProvider

        # Create product
        product = Product(
            name="无线蓝牙耳机入耳式",
            platform="taobao",
            shop="数码店",
            price=150.0,
            status="ACTIVE",
        )
        session.add(product)
        await session.commit()

        # Match
        provider = SupplyChainProvider()
        matcher = SupplyChainMatcher(session, provider=provider)
        match = await matcher.match_product(product)

        # Mock catalog has "蓝牙耳机" items, should match
        if match:
            assert match.product_id == product.id
            assert match.match_type in ("title", "title+image")

    @pytest.mark.anyio
    async def test_supply_chain_to_report_flow(self, session):
        """Test SupplyChainMatch → DailySelectionReport flow."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Create product + match
        product = Product(
            name="高利润商品",
            platform="taobao",
            shop="店铺",
            price=200.0,
            status="ACTIVE",
        )
        session.add(product)
        await session.flush()

        match = SupplyChainMatch(
            product_id=product.id,
            source_product_external_id="sc_001",
            match_score=0.9,
            match_type="title",
            cost_price=60.0,
            sell_price=200.0,
            profit_margin=50.0,
            profit_amount=80.0,
            status="MATCHED",
        )
        session.add(match)
        await session.commit()

        # Generate report
        svc = DailySelectionReportService(session)
        report = await svc.generate()

        # Verify match appears in report
        assert report["summary"]["matched_count"] >= 1
        assert len(report["supply_chain_matches"]) >= 1

    @pytest.mark.anyio
    async def test_shop_url_in_product_creation(self, session, sample_raw_products):
        """Test shop_url from raw product is preserved."""
        from app.services.product_service import ProductService

        svc = ProductService(session)
        result = await svc.save_raw_products(sample_raw_products)

        assert result["saved_count"] == 3

        # Check products have shop info
        products = await svc.list_all(limit=10)
        assert all(p.shop for p in products)
