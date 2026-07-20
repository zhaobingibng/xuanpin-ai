"""Tests for DashboardService — overview statistics."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.crawler_status import CrawlerStatus
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.services.dashboard.service import DashboardService

# ensure models registered
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


# ── Overview statistics ──────────────────────────────────────


class TestOverviewStatistics:
    """overview 统计验证。"""

    @pytest.mark.anyio
    async def test_overview_empty_db(self, session):
        """空数据库 → 所有计数为 0。"""
        svc = DashboardService(session)
        overview = await svc.overview()

        assert overview["products"] == 0
        assert overview["today_crawl"] == 0
        assert overview["hot_products"] == 0
        assert overview["rising_products"] == 0
        assert overview["today_recommendations"] == 0
        assert overview["average_score"] == 0.0

    @pytest.mark.anyio
    async def test_overview_product_count(self, session):
        """商品计数应正确。"""
        for i in range(3):
            session.add(Product(
                name=f"商品{i}", platform="xiaohongshu", shop="店铺",
                price=99.0, sales_24h=100, viewers=1000,
            ))
        await session.commit()

        svc = DashboardService(session)
        overview = await svc.overview()
        assert overview["products"] == 3

    @pytest.mark.anyio
    async def test_overview_lifecycle_counts(self, session):
        """HOT/RISING 计数应正确。"""
        session.add(Product(
            name="HOT商品", platform="xhs", shop="s", price=99.0,
            lifecycle_stage="HOT", sales_24h=5000, viewers=10000,
        ))
        session.add(Product(
            name="RISING商品", platform="xhs", shop="s", price=99.0,
            lifecycle_stage="RISING", sales_24h=2000, viewers=5000,
        ))
        session.add(Product(
            name="NEW商品", platform="xhs", shop="s", price=99.0,
            lifecycle_stage="NEW", sales_24h=100, viewers=500,
        ))
        await session.commit()

        svc = DashboardService(session)
        overview = await svc.overview()
        assert overview["hot_products"] == 1
        assert overview["rising_products"] == 1

    @pytest.mark.anyio
    async def test_overview_today_recommendations(self, session):
        """今日推荐数和平均分应从日报读取。"""
        from datetime import date
        report = DailyReport(
            report_date=date.today(),
            total=5,
            hot_products=2,
            potential_products=3,
            average_score=85.5,
        )
        session.add(report)
        await session.flush()

        item = DailyReportItem(
            report_id=report.id, product_id=1, rank=1,
            name="商品A", platform="xhs", price=99.0,
            score=85, level="潜力", reasons="[]",
        )
        session.add(item)
        await session.commit()

        svc = DashboardService(session)
        overview = await svc.overview()
        assert overview["today_recommendations"] == 5
        assert overview["average_score"] == 85.5


# ── Category/Platform distribution ───────────────────────────


class TestDistribution:
    """分类/平台分布统计。"""

    @pytest.mark.anyio
    async def test_platform_distribution(self, session):
        """平台分布应正确统计。"""
        session.add(Product(name="A", platform="xiaohongshu", shop="s", price=99.0))
        session.add(Product(name="B", platform="xiaohongshu", shop="s", price=99.0))
        session.add(Product(name="C", platform="douyin", shop="s", price=99.0))
        await session.commit()

        svc = DashboardService(session)
        overview = await svc.overview()
        dist = overview["platform_distribution"]
        assert dist["xiaohongshu"] == 2
        assert dist["douyin"] == 1

    @pytest.mark.anyio
    async def test_category_distribution(self, session):
        """分类分布应正确统计，None 分类排除。"""
        session.add(Product(name="A", platform="xhs", shop="s", price=99.0, category="美妆"))
        session.add(Product(name="B", platform="xhs", shop="s", price=99.0, category="美妆"))
        session.add(Product(name="C", platform="xhs", shop="s", price=99.0, category="食品"))
        session.add(Product(name="D", platform="xhs", shop="s", price=99.0, category=None))
        await session.commit()

        svc = DashboardService(session)
        overview = await svc.overview()
        dist = overview["category_distribution"]
        assert dist["美妆"] == 2
        assert dist["食品"] == 1
        assert None not in dist
