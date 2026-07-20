"""Tests for DailyReportService.generate_and_save and scheduler integration."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.report_repository import ReportRepository
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.services.report.daily_report import DailyReportService

import app.models  # noqa: F401


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


async def _insert_products(session: AsyncSession, count: int = 3) -> None:
    """Insert sample products for report generation."""
    for i in range(count):
        p = Product(
            name=f"测试商品{i + 1}",
            platform="xiaohongshu",
            shop="测试店铺",
            price=99.0 + i * 10,
            viewers=5000 - i * 500,
            sales_24h=1000 - i * 100,
        )
        session.add(p)
    await session.commit()


class TestGenerateAndSave:

    @pytest.mark.asyncio
    async def test_generate_and_save_creates_report(self, session):
        """generate_and_save should create a DailyReport + items in DB."""
        await _insert_products(session, 3)

        svc = DailyReportService(session)
        report = await svc.generate_and_save(limit=20)

        assert report["total"] > 0
        assert "items" in report

        # Verify persisted in DB
        repo = ReportRepository(session)
        latest = await repo.get_latest()
        assert latest is not None
        assert latest.report_date == date.today()
        assert latest.total == report["total"]

    @pytest.mark.asyncio
    async def test_generate_and_save_empty(self, session):
        """generate_and_save with no products should still create a report."""
        svc = DailyReportService(session)
        report = await svc.generate_and_save()

        assert report["total"] == 0
        assert report["items"] == []

        repo = ReportRepository(session)
        latest = await repo.get_latest()
        assert latest is not None
        assert latest.total == 0

    @pytest.mark.asyncio
    async def test_generate_and_save_items_persisted(self, session):
        """Items should be persisted with correct fields."""
        await _insert_products(session, 5)

        svc = DailyReportService(session)
        report = await svc.generate_and_save(limit=3)

        repo = ReportRepository(session)
        latest = await repo.get_latest()
        assert latest is not None
        assert len(latest.items) == 3
        assert all(item.rank > 0 for item in latest.items)
        assert all(item.name != "" for item in latest.items)


class TestDuplicateGeneration:

    @pytest.mark.asyncio
    async def test_duplicate_updates_existing(self, session):
        """Second generate_and_save on same day should update, not create duplicate."""
        await _insert_products(session, 3)

        svc = DailyReportService(session)

        # First generation
        report1 = await svc.generate_and_save(limit=20)
        repo = ReportRepository(session)
        first = await repo.get_latest()
        first_id = first.id

        # Second generation (same day)
        report2 = await svc.generate_and_save(limit=20)
        second = await repo.get_latest()

        # Should be the same record (updated, not new)
        assert second.id == first_id
        assert second.report_date == date.today()

    @pytest.mark.asyncio
    async def test_duplicate_no_extra_records(self, session):
        """Two generate_and_save calls should result in exactly one record."""
        await _insert_products(session, 2)

        svc = DailyReportService(session)
        await svc.generate_and_save()
        await svc.generate_and_save()

        history = await ReportRepository(session).get_history()
        assert len(history) == 1


class TestSchedulerCallsGenerateAndSave:

    @pytest.mark.asyncio
    async def test_daily_crawl_job_calls_generate_and_save(self):
        """daily_crawl_job should call generate_and_save after save step."""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="蓝牙耳机降噪",
                platform="xiaohongshu",
                shop="数码店",
                price=99.9,
                viewers=5000,
                sales_24h=1200,
            ),
        ]

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_report_svc = AsyncMock()
        mock_report_svc.generate_and_save.return_value = {
            "date": "2026-07-19",
            "total": 1,
            "items": [],
        }

        mock_product_svc = AsyncMock()
        mock_product_svc.save_raw_products = AsyncMock(return_value=1)

        with (
            patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls,
            patch("app.services.product_service.ProductService", return_value=mock_product_svc),
            patch("app.database.base.get_async_session_factory", return_value=mock_factory),
            patch("app.services.report.daily_report.DailyReportService", return_value=mock_report_svc),
        ):
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            from app.tasks.jobs import daily_crawl_job
            result = await daily_crawl_job(
                keywords=["耳机"],
                platforms=["xiaohongshu"],
                save_to_db=True,
            )

        mock_report_svc.generate_and_save.assert_awaited_once()
        assert "report_date" in result

    @pytest.mark.asyncio
    async def test_report_failure_does_not_stop_job(self):
        """Report generation failure should not stop the crawl job."""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="保温杯",
                platform="xiaohongshu",
                shop="家居店",
                price=49.9,
                viewers=3000,
                sales_24h=800,
            ),
        ]

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls,
            patch("app.services.product_service.ProductService") as mock_product_svc_cls,
            patch("app.database.base.get_async_session_factory", return_value=mock_factory),
            patch("app.services.report.daily_report.DailyReportService", side_effect=RuntimeError("report error")),
        ):
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            mock_product_svc = AsyncMock()
            mock_product_svc.save_raw_products = AsyncMock(return_value=1)
            mock_product_svc_cls.return_value = mock_product_svc

            from app.tasks.jobs import daily_crawl_job
            result = await daily_crawl_job(
                keywords=["水杯"],
                platforms=["xiaohongshu"],
                save_to_db=True,
            )

        # Job should complete despite report failure
        assert result["raw_count"] == 1
        assert any("report error" in e for e in result["errors"])
