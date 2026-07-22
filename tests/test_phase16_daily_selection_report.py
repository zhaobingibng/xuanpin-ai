"""Tests for DailySelectionReportService."""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ============================================================
# DailySelectionReportService Tests
# ============================================================


class TestDailySelectionReportService:
    """Test daily selection report generation."""

    def test_import(self):
        """Test module imports correctly."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        assert DailySelectionReportService is not None

    @pytest.mark.anyio
    async def test_generate_empty_db(self, session):
        """Test generate with empty database."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        svc = DailySelectionReportService(session)
        report = await svc.generate()

        assert report["date"] == date.today().isoformat()
        assert "generated_at" in report
        assert report["new_products"] == []
        assert report["supply_chain_matches"] == []
        assert report["top_picks"] == []
        assert report["summary"]["new_products_count"] == 0
        assert report["summary"]["matched_count"] == 0

    @pytest.mark.anyio
    async def test_generate_with_new_products(self, session):
        """Test generate collects new products."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Create a recent product
        product = Product(
            name="测试新品",
            platform="taobao",
            shop="测试店铺",
            price=99.0,
            ai_score=80,
            status="ACTIVE",
            created_at=datetime.now(),
        )
        session.add(product)
        await session.commit()

        svc = DailySelectionReportService(session)
        report = await svc.generate()

        assert report["summary"]["new_products_count"] >= 1
        assert any(p["name"] == "测试新品" for p in report["new_products"])

    @pytest.mark.anyio
    async def test_generate_with_supply_chain_matches(self, session):
        """Test generate collects supply chain matches."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Create product
        product = Product(
            name="匹配商品",
            platform="taobao",
            shop="测试店铺",
            price=150.0,
            status="ACTIVE",
        )
        session.add(product)
        await session.flush()

        # Create match
        match = SupplyChainMatch(
            product_id=product.id,
            source_product_external_id="sc_001",
            match_score=0.85,
            match_type="title",
            cost_price=50.0,
            sell_price=150.0,
            profit_margin=40.0,
            profit_amount=55.0,
            status="MATCHED",
        )
        session.add(match)
        await session.commit()

        svc = DailySelectionReportService(session)
        report = await svc.generate()

        assert report["summary"]["matched_count"] >= 1
        assert any(m["product_name"] == "匹配商品" for m in report["supply_chain_matches"])

    @pytest.mark.anyio
    async def test_profit_analysis(self, session):
        """Test profit analysis calculation."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Create products with different margins
        for i, margin in enumerate([45.0, 25.0, 10.0, -5.0]):
            product = Product(
                name=f"商品{i}",
                platform="taobao",
                shop="店铺",
                price=100.0,
                status="ACTIVE",
            )
            session.add(product)
            await session.flush()

            match = SupplyChainMatch(
                product_id=product.id,
                source_product_external_id=f"sc_{i}",
                match_score=0.7,
                match_type="title",
                cost_price=50.0,
                sell_price=100.0,
                profit_margin=margin,
                profit_amount=margin,
                status="MATCHED",
            )
            session.add(match)

        await session.commit()

        svc = DailySelectionReportService(session)
        report = await svc.generate()

        analysis = report["profit_analysis"]
        assert analysis["total_matches"] >= 4
        assert analysis["high_profit_count"] >= 1  # margin >= 30
        assert analysis["medium_profit_count"] >= 1  # 15 <= margin < 30
        assert analysis["low_profit_count"] >= 1  # 0 <= margin < 15
        assert analysis["negative_profit_count"] >= 1  # margin < 0

    @pytest.mark.anyio
    async def test_ai_recommendations(self, session):
        """Test AI recommendations generation."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # High profit product
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
            source_product_external_id="sc_hp",
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

        svc = DailySelectionReportService(session)
        report = await svc.generate()

        # Should have recommendation for high profit
        assert len(report["ai_recommendations"]) >= 1
        assert any(r["reason"] == "high_profit" for r in report["ai_recommendations"])

    @pytest.mark.anyio
    async def test_top_picks_selection(self, session):
        """Test top picks selection logic."""
        from app.services.report.daily_selection_report import DailySelectionReportService

        # Create high profit product
        product = Product(
            name="精选商品",
            platform="taobao",
            shop="店铺",
            price=180.0,
            status="ACTIVE",
        )
        session.add(product)
        await session.flush()

        match = SupplyChainMatch(
            product_id=product.id,
            source_product_external_id="sc_top",
            match_score=0.95,
            match_type="title",
            cost_price=50.0,
            sell_price=180.0,
            profit_margin=55.0,
            profit_amount=85.0,
            status="MATCHED",
        )
        session.add(match)
        await session.commit()

        svc = DailySelectionReportService(session)
        report = await svc.generate()

        # Should be in top picks
        assert len(report["top_picks"]) >= 1
        assert any(p["product_name"] == "精选商品" for p in report["top_picks"])

    @pytest.mark.anyio
    async def test_summary_structure(self, session):
        """Test summary has required fields."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        svc = DailySelectionReportService(session)
        report = await svc.generate()

        summary = report["summary"]
        assert "new_products_count" in summary
        assert "matched_count" in summary
        assert "avg_profit_margin" in summary
        assert "high_profit_count" in summary
        assert "recommendation_count" in summary

    @pytest.mark.anyio
    async def test_report_structure(self, session):
        """Test report has all required sections."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        svc = DailySelectionReportService(session)
        report = await svc.generate()

        assert "date" in report
        assert "generated_at" in report
        assert "summary" in report
        assert "new_products" in report
        assert "supply_chain_matches" in report
        assert "profit_analysis" in report
        assert "ai_recommendations" in report
        assert "top_picks" in report

    def test_analyze_profits_empty(self):
        """Test profit analysis with empty data."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        session = MagicMock()
        svc = DailySelectionReportService(session)
        analysis = svc._analyze_profits([])

        assert analysis["total_matches"] == 0
        assert analysis["avg_margin"] == 0.0

    def test_analyze_profits_calculation(self):
        """Test profit analysis calculation."""
        from app.services.report.daily_selection_report import DailySelectionReportService
        session = MagicMock()
        svc = DailySelectionReportService(session)

        matches = [
            {"profit_margin": 40.0},
            {"profit_margin": 20.0},
            {"profit_margin": 5.0},
            {"profit_margin": -10.0},
        ]
        analysis = svc._analyze_profits(matches)

        assert analysis["total_matches"] == 4
        assert analysis["avg_margin"] == 13.75  # (40+20+5-10)/4
        assert analysis["max_margin"] == 40.0
        assert analysis["min_margin"] == -10.0
        assert analysis["high_profit_count"] == 1
        assert analysis["medium_profit_count"] == 1
        assert analysis["low_profit_count"] == 1
        assert analysis["negative_profit_count"] == 1


# ============================================================
# Pipeline Integration Test
# ============================================================


class TestPipelineStep14:
    """Test Pipeline Step 14 integration."""

    def test_step_14_exists_in_jobs(self):
        """Test Step 14 is defined in jobs.py."""
        import inspect
        from app.tasks import jobs
        source = inspect.getsource(jobs)
        assert "Step 14" in source
        assert "DailySelectionReportService" in source
