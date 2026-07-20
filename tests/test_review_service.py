"""Tests for RecommendationReviewService — SUCCESS/NORMAL/FAILED judgement, accuracy."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.history_repository import HistoryRepository
from app.database.report_repository import ReportRepository
from app.database.review_repository import ReviewRepository
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.review.analyzer import RecommendationReviewService

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


async def _seed_product(session: AsyncSession, name: str = "测试商品", price: float = 99.0) -> Product:
    p = Product(name=name, platform="xiaohongshu", shop="测试店铺", price=price, sales_24h=50, viewers=200)
    session.add(p)
    await session.flush()
    return p


async def _seed_history(
    session: AsyncSession,
    product_id: int,
    sales: int = 50,
    viewers: int = 200,
    days_ago: int = 10,
) -> ProductHistory:
    h = ProductHistory(
        product_id=product_id,
        price=99.0,
        sales_24h=sales,
        viewers=viewers,
        record_time=datetime.utcnow() - timedelta(days=days_ago),
    )
    session.add(h)
    await session.flush()
    return h


async def _seed_report_with_items(
    session: AsyncSession,
    report_date: date,
    items: list[dict],
) -> DailyReport:
    """Create a DailyReport with items."""
    report = DailyReport(
        report_date=report_date,
        total=len(items),
        hot_products=0,
        potential_products=0,
        average_score=0.0,
    )
    session.add(report)
    await session.flush()

    for entry in items:
        item = DailyReportItem(
            report_id=report.id,
            product_id=entry["product_id"],
            rank=entry.get("rank", 1),
            name=entry.get("name", "商品"),
            platform=entry.get("platform", "xiaohongshu"),
            image="",
            price=entry.get("price", 99.0),
            score=entry.get("score", 80),
            level="潜力",
            reasons="[]",
        )
        session.add(item)
    await session.flush()
    return report


# ── Judgement logic ──────────────────────────────────────


class TestJudgeResult:
    """_judge_result 静态方法测试。"""

    def test_success_sales_growth(self):
        """销量增长 >=30% → SUCCESS。"""
        assert RecommendationReviewService._judge_result(30.0, 0.0) == "SUCCESS"
        assert RecommendationReviewService._judge_result(50.0, 0.0) == "SUCCESS"
        assert RecommendationReviewService._judge_result(100.0, 0.0) == "SUCCESS"

    def test_success_trend_growth(self):
        """trend 提升 >=20 → SUCCESS。"""
        assert RecommendationReviewService._judge_result(0.0, 20.0) == "SUCCESS"
        assert RecommendationReviewService._judge_result(0.0, 50.0) == "SUCCESS"

    def test_failed_sales_drop(self):
        """销量下降 >30% → FAILED。"""
        assert RecommendationReviewService._judge_result(-30.0, 0.0) == "FAILED"
        assert RecommendationReviewService._judge_result(-50.0, 0.0) == "FAILED"

    def test_failed_trend_drop(self):
        """trend 下降 <= -20 → FAILED。"""
        assert RecommendationReviewService._judge_result(0.0, -20.0) == "FAILED"
        assert RecommendationReviewService._judge_result(0.0, -50.0) == "FAILED"

    def test_normal_no_change(self):
        """无明显变化 → NORMAL。"""
        assert RecommendationReviewService._judge_result(0.0, 0.0) == "NORMAL"
        assert RecommendationReviewService._judge_result(10.0, 5.0) == "NORMAL"
        assert RecommendationReviewService._judge_result(-10.0, -5.0) == "NORMAL"

    def test_success_overrides_failed(self):
        """销量增长但趋势下降时，SUCCESS 优先。"""
        # sales +50% but trend -30 → sales >=30 triggers SUCCESS
        assert RecommendationReviewService._judge_result(50.0, -30.0) == "SUCCESS"


# ── Full pipeline tests ──────────────────────────────────


class TestReviewDaily:
    """完整复盘流程。"""

    @pytest.mark.anyio
    async def test_no_report(self, session):
        """无推荐记录时返回空结果。"""
        svc = RecommendationReviewService(session)
        result = await svc.review_daily(date(2026, 7, 1))
        assert result["total"] == 0
        assert result["accuracy"] == 0.0
        assert "无推荐记录" in result["insights"]

    @pytest.mark.anyio
    async def test_review_with_no_history(self, session):
        """商品无历史数据时判为 NORMAL。"""
        p = await _seed_product(session)
        await session.commit()

        report_date = date.today() - timedelta(days=7)
        await _seed_report_with_items(session, report_date, [
            {"product_id": p.id, "rank": 1},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(report_date)
        assert result["total"] == 1
        assert result["normal"] == 1

    @pytest.mark.anyio
    async def test_review_success(self, session):
        """销量增长 >=30% → SUCCESS。"""
        p = await _seed_product(session)
        await session.commit()

        report_date = date.today() - timedelta(days=7)

        # 推荐前：sales=50
        await _seed_history(session, p.id, sales=50, viewers=200, days_ago=10)
        # 推荐后：sales=100（增长 100%）
        await _seed_history(session, p.id, sales=100, viewers=300, days_ago=1)
        await session.commit()

        await _seed_report_with_items(session, report_date, [
            {"product_id": p.id, "rank": 1},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(report_date)
        assert result["total"] == 1
        assert result["success"] == 1
        assert result["accuracy"] == 100.0

    @pytest.mark.anyio
    async def test_review_failed(self, session):
        """销量下降 >30% → FAILED。"""
        p = await _seed_product(session)
        await session.commit()

        report_date = date.today() - timedelta(days=7)

        # 推荐前：sales=100
        await _seed_history(session, p.id, sales=100, viewers=500, days_ago=10)
        # 推荐后：sales=30（下降 70%）
        await _seed_history(session, p.id, sales=30, viewers=100, days_ago=1)
        await session.commit()

        await _seed_report_with_items(session, report_date, [
            {"product_id": p.id, "rank": 1},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(report_date)
        assert result["total"] == 1
        assert result["failed"] == 1
        assert result["accuracy"] == 0.0

    @pytest.mark.anyio
    async def test_review_mixed_results(self, session):
        """混合结果验证准确率。"""
        p1 = await _seed_product(session, "商品A")
        p2 = await _seed_product(session, "商品B")
        p3 = await _seed_product(session, "商品C")
        await session.commit()

        report_date = date.today() - timedelta(days=7)

        # p1: 增长 → SUCCESS
        await _seed_history(session, p1.id, sales=50, viewers=200, days_ago=10)
        await _seed_history(session, p1.id, sales=100, viewers=400, days_ago=1)

        # p2: 下降 → FAILED
        await _seed_history(session, p2.id, sales=100, viewers=500, days_ago=10)
        await _seed_history(session, p2.id, sales=30, viewers=100, days_ago=1)

        # p3: 无明显变化 → NORMAL
        await _seed_history(session, p3.id, sales=50, viewers=200, days_ago=10)
        await _seed_history(session, p3.id, sales=55, viewers=210, days_ago=1)
        await session.commit()

        await _seed_report_with_items(session, report_date, [
            {"product_id": p1.id, "rank": 1},
            {"product_id": p2.id, "rank": 2},
            {"product_id": p3.id, "rank": 3},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(report_date)
        assert result["total"] == 3
        assert result["success"] == 1
        assert result["failed"] == 1
        assert result["normal"] == 1
        # accuracy = 1/3 * 100 ≈ 33.3%
        assert result["accuracy"] == pytest.approx(33.3, abs=0.1)

    @pytest.mark.anyio
    async def test_review_saves_to_repository(self, session):
        """复盘结果应保存到 ReviewRepository。"""
        p = await _seed_product(session)
        await _seed_history(session, p.id, sales=50, viewers=200, days_ago=10)
        await _seed_history(session, p.id, sales=100, viewers=400, days_ago=1)
        await session.commit()

        report_date = date.today() - timedelta(days=7)
        await _seed_report_with_items(session, report_date, [
            {"product_id": p.id, "rank": 1},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        await svc.review_daily(report_date)

        repo = ReviewRepository(session)
        records = await repo.get_reviews()
        assert len(records) == 1
        assert records[0].product_id == p.id

    @pytest.mark.anyio
    async def test_insights_generated(self, session):
        """复盘应生成 insights 列表。"""
        p = await _seed_product(session)
        await _seed_history(session, p.id, sales=50, viewers=200, days_ago=10)
        await _seed_history(session, p.id, sales=100, viewers=400, days_ago=1)
        await session.commit()

        report_date = date.today() - timedelta(days=7)
        await _seed_report_with_items(session, report_date, [
            {"product_id": p.id, "rank": 1},
        ])
        await session.commit()

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(report_date)
        assert isinstance(result["insights"], list)
        assert len(result["insights"]) >= 2


# ── Calc change helper ───────────────────────────────────


class TestCalcChange:
    """_calc_change 静态方法测试。"""

    def test_positive_change(self):
        assert RecommendationReviewService._calc_change(100, 150) == 50.0

    def test_negative_change(self):
        assert RecommendationReviewService._calc_change(100, 70) == -30.0

    def test_zero_baseline(self):
        assert RecommendationReviewService._calc_change(0, 50) == 100.0

    def test_both_zero(self):
        assert RecommendationReviewService._calc_change(0, 0) == 0.0

    def test_no_change(self):
        assert RecommendationReviewService._calc_change(100, 100) == 0.0


# ── Accuracy ─────────────────────────────────────────────


class TestAccuracy:
    """准确率计算。"""

    @pytest.mark.anyio
    async def test_empty_accuracy(self, session):
        """无复盘记录时准确率为 0。"""
        repo = ReviewRepository(session)
        result = await repo.get_accuracy()
        assert result["accuracy"] == 0.0
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_accuracy_calculation(self, session):
        """准确率 = success / total * 100。"""
        from app.models.recommendation_review import RecommendationReview

        # 3 SUCCESS, 2 FAILED → 60%
        for i, r in enumerate(["SUCCESS", "SUCCESS", "SUCCESS", "FAILED", "FAILED"]):
            review = RecommendationReview(
                recommendation_id=i + 1,
                product_id=i + 1,
                review_date=date.today(),
                result=r,
                sales_change=10.0,
                trend_change=5.0,
            )
            session.add(review)
        await session.commit()

        repo = ReviewRepository(session)
        result = await repo.get_accuracy()
        assert result["accuracy"] == 60.0
        assert result["total"] == 5
        assert result["success"] == 3
