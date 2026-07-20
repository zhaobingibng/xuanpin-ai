"""Tests for ReportRepository."""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.report_repository import ReportRepository
from app.models.daily_report import DailyReport, DailyReportItem

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


def _sample_items(n: int = 3) -> list[dict]:
    return [
        {
            "rank": i + 1,
            "product_id": i + 1,
            "name": f"商品{i + 1}",
            "platform": "xiaohongshu",
            "image": f"https://img.example.com/{i + 1}.jpg",
            "price": 99.0 + i * 10,
            "score": 90 - i * 5,
            "level": "爆款" if i == 0 else "潜力",
            "reasons": ["销量高", "增长快"],
        }
        for i in range(n)
    ]


class TestCreateReport:

    @pytest.mark.asyncio
    async def test_create_report(self, session):
        """create_report should insert and return the report."""
        repo = ReportRepository(session)
        report = DailyReport(
            report_date=date(2026, 7, 1),
            total=5,
            hot_products=2,
            potential_products=2,
            average_score=80.0,
        )
        result = await repo.create_report(report)
        assert result.id is not None
        assert result.report_date == date(2026, 7, 1)
        assert result.total == 5


class TestSaveItems:

    @pytest.mark.asyncio
    async def test_save_items(self, session):
        """save_items should batch-insert items for a report."""
        repo = ReportRepository(session)
        report = DailyReport(
            report_date=date(2026, 7, 1),
            total=3,
            hot_products=1,
            potential_products=1,
            average_score=85.0,
        )
        await repo.create_report(report)

        items = _sample_items(3)
        created = await repo.save_items(report.id, items)
        assert len(created) == 3
        assert all(item.report_id == report.id for item in created)
        assert created[0].rank == 1
        assert created[0].name == "商品1"

    @pytest.mark.asyncio
    async def test_save_items_reasons_json(self, session):
        """reasons should be stored as JSON string."""
        repo = ReportRepository(session)
        report = DailyReport(
            report_date=date(2026, 7, 1),
            total=1,
            hot_products=1,
            potential_products=0,
            average_score=90.0,
        )
        await repo.create_report(report)

        items = [{"rank": 1, "product_id": 1, "name": "测试", "platform": "douyin",
                   "image": "", "price": 50.0, "score": 90, "level": "爆款",
                   "reasons": ["理由A", "理由B"]}]
        created = await repo.save_items(report.id, items)
        assert "理由A" in created[0].reasons
        assert "理由B" in created[0].reasons


class TestGetLatest:

    @pytest.mark.asyncio
    async def test_get_latest_empty(self, session):
        """get_latest with no data should return None."""
        repo = ReportRepository(session)
        result = await repo.get_latest()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_returns_newest(self, session):
        """get_latest should return the most recent report."""
        repo = ReportRepository(session)
        r1 = DailyReport(report_date=date(2026, 7, 1), total=5, hot_products=1, potential_products=2, average_score=70.0)
        r2 = DailyReport(report_date=date(2026, 7, 2), total=10, hot_products=3, potential_products=4, average_score=85.0)
        await repo.create_report(r1)
        await repo.create_report(r2)

        latest = await repo.get_latest()
        assert latest is not None
        assert latest.report_date == date(2026, 7, 2)
        assert latest.total == 10


class TestGetHistory:

    @pytest.mark.asyncio
    async def test_get_history_empty(self, session):
        """get_history with no data should return empty list."""
        repo = ReportRepository(session)
        result = await repo.get_history()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_history_ordered(self, session):
        """get_history should return reports ordered by date desc."""
        repo = ReportRepository(session)
        for i in range(5):
            r = DailyReport(
                report_date=date(2026, 7, 1) + timedelta(days=i),
                total=i + 1,
                hot_products=0,
                potential_products=0,
                average_score=0.0,
            )
            await repo.create_report(r)

        history = await repo.get_history(limit=3)
        assert len(history) == 3
        assert history[0].report_date == date(2026, 7, 5)
        assert history[2].report_date == date(2026, 7, 3)

    @pytest.mark.asyncio
    async def test_get_history_limit(self, session):
        """get_history limit should cap results."""
        repo = ReportRepository(session)
        for i in range(10):
            r = DailyReport(
                report_date=date(2026, 7, 1) + timedelta(days=i),
                total=1,
                hot_products=0,
                potential_products=0,
                average_score=0.0,
            )
            await repo.create_report(r)

        history = await repo.get_history(limit=5)
        assert len(history) == 5


class TestGetReportDetail:

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, session):
        """get_report_detail with nonexistent id should return None."""
        repo = ReportRepository(session)
        result = await repo.get_report_detail(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_detail_with_items(self, session):
        """get_report_detail should include items."""
        repo = ReportRepository(session)
        report = DailyReport(
            report_date=date(2026, 7, 1),
            total=2,
            hot_products=1,
            potential_products=1,
            average_score=85.0,
        )
        await repo.create_report(report)
        await repo.save_items(report.id, _sample_items(2))

        detail = await repo.get_report_detail(report.id)
        assert detail is not None
        assert len(detail.items) == 2
        assert detail.items[0].rank in (1, 2)


class TestFindByDate:

    @pytest.mark.asyncio
    async def test_find_by_date_not_found(self, session):
        """find_by_date should return None when no report exists."""
        repo = ReportRepository(session)
        result = await repo.find_by_date(date(2099, 1, 1))
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_date_found(self, session):
        """find_by_date should return the matching report."""
        repo = ReportRepository(session)
        report = DailyReport(
            report_date=date(2026, 7, 19),
            total=5,
            hot_products=2,
            potential_products=1,
            average_score=80.0,
        )
        await repo.create_report(report)

        found = await repo.find_by_date(date(2026, 7, 19))
        assert found is not None
        assert found.total == 5
