"""Tests for DailyReportService."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.history_repository import HistoryRepository
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.product_service import ProductService
from app.services.report.daily_report import DailyReportService

# ensure models registered
import app.models  # noqa: F401


# ── Fixtures ─────────────────────────────────────────────────


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


async def _seed_product(
    session: AsyncSession,
    *,
    name: str = "测试商品",
    price: float = 99.0,
    sales_24h: int = 500,
    viewers: int = 2000,
    platform: str = "xiaohongshu",
    image: str | None = None,
) -> Product:
    product = Product(
        name=name, platform=platform, shop="测试店铺",
        price=price, sales_24h=sales_24h, viewers=viewers, image=image,
    )
    session.add(product)
    await session.flush()
    return product


async def _seed_history(
    session: AsyncSession,
    product_id: int,
    sales: list[int],
    price: float = 99.0,
) -> None:
    now = datetime.utcnow()
    for i, s in enumerate(sales):
        h = ProductHistory(
            product_id=product_id, price=price,
            sales_24h=s, viewers=0,
            record_time=now - timedelta(minutes=(len(sales) - i) * 60),
        )
        session.add(h)
    await session.flush()


# ── TestEmptyData ────────────────────────────────────────────


class TestEmptyData:

    @pytest.mark.anyio
    async def test_empty_db_returns_zero(self, session):
        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["total"] == 0
        assert report["items"] == []
        assert report["hot_products"] == 0
        assert report["potential_products"] == 0
        assert report["average_score"] == 0.0

    @pytest.mark.anyio
    async def test_empty_report_has_date(self, session):
        svc = DailyReportService(session)
        report = await svc.generate()

        assert "date" in report
        assert len(report["date"]) == 10  # YYYY-MM-DD


# ── TestSingleProduct ───────────────────────────────────────


class TestSingleProduct:

    @pytest.mark.anyio
    async def test_single_product_report(self, session):
        p = await _seed_product(session, name="蓝牙耳机", sales_24h=500, price=99.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["total"] == 1
        assert len(report["items"]) == 1
        item = report["items"][0]
        assert item["rank"] == 1
        assert item["name"] == "蓝牙耳机"
        assert item["product_id"] == p.id

    @pytest.mark.anyio
    async def test_single_product_score_and_level(self, session):
        await _seed_product(session, sales_24h=500, viewers=2000, price=99.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        item = report["items"][0]
        assert isinstance(item["score"], int)
        assert item["score"] > 0
        assert item["level"] in ("爆款", "潜力", "一般", "低潜")


# ── TestTopLimit ─────────────────────────────────────────────


class TestTopLimit:

    @pytest.mark.anyio
    async def test_default_limit_20(self, session):
        for i in range(25):
            await _seed_product(session, name=f"商品{i}", sales_24h=100 + i)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["total"] == 20
        assert len(report["items"]) == 20

    @pytest.mark.anyio
    async def test_custom_limit(self, session):
        for i in range(10):
            await _seed_product(session, name=f"商品{i}", sales_24h=100 + i)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate(limit=5)

        assert report["total"] == 5
        assert len(report["items"]) == 5

    @pytest.mark.anyio
    async def test_limit_greater_than_products(self, session):
        for i in range(3):
            await _seed_product(session, name=f"商品{i}", sales_24h=100 + i)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate(limit=20)

        assert report["total"] == 3
        assert len(report["items"]) == 3


# ── TestSorting ──────────────────────────────────────────────


class TestSorting:

    @pytest.mark.anyio
    async def test_sorted_by_score_desc(self, session):
        await _seed_product(session, name="低销量", sales_24h=10, viewers=50, price=5.0)
        await _seed_product(session, name="高销量", sales_24h=12000, viewers=60000, price=99.0)
        await _seed_product(session, name="中销量", sales_24h=1500, viewers=2000, price=50.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        scores = [item["score"] for item in report["items"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.anyio
    async def test_rank_assignment(self, session):
        for i in range(5):
            await _seed_product(session, name=f"商品{i}", sales_24h=100 * (i + 1))
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        ranks = [item["rank"] for item in report["items"]]
        assert ranks == list(range(1, 6))

    @pytest.mark.anyio
    async def test_highest_score_gets_rank_1(self, session):
        await _seed_product(session, name="低", sales_24h=10, viewers=50, price=5.0)
        await _seed_product(session, name="高", sales_24h=12000, viewers=60000, price=99.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["items"][0]["rank"] == 1
        assert report["items"][0]["name"] == "高"


# ── TestScorerIntegration ───────────────────────────────────


class TestScorerIntegration:

    @pytest.mark.anyio
    async def test_scorer_uses_history(self, session):
        p = await _seed_product(session, sales_24h=5000, viewers=20000, price=99.0)
        # Add history with growth: 100 → 5000 (4900% growth → 25 trend points)
        await _seed_history(session, p.id, sales=[100, 5000])
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        item = report["items"][0]
        # With history: sales(25) + trend(25) + viewers(10) + price(15) + profit(10) = 85
        assert item["score"] >= 80
        assert any("增长率" in r for r in item["reasons"])

    @pytest.mark.anyio
    async def test_scorer_without_history(self, session):
        await _seed_product(session, sales_24h=500, price=99.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        item = report["items"][0]
        assert any("暂无趋势数据" in r for r in item["reasons"])


# ── TestLevelStatistics ─────────────────────────────────────


class TestLevelStatistics:

    @pytest.mark.anyio
    async def test_hot_products_count(self, session):
        # Create a product that scores >= 90 (爆款)
        p = await _seed_product(
            session, name="爆款", sales_24h=12000, viewers=60000, price=99.0,
        )
        await _seed_history(session, p.id, sales=[100, 500])  # 400% → 25 trend
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["hot_products"] == 1
        assert report["items"][0]["level"] == "爆款"

    @pytest.mark.anyio
    async def test_potential_products_count(self, session):
        # 潜力: score 70-89
        p = await _seed_product(
            session, name="潜力", sales_24h=6000, viewers=15000, price=100.0,
        )
        await _seed_history(session, p.id, sales=[100, 160])  # 60% → 20 trend
        # sales(25) + trend(20) + viewers(10) + price(15) + profit(10) = 80
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["potential_products"] == 1
        assert report["items"][0]["level"] == "潜力"

    @pytest.mark.anyio
    async def test_mixed_levels(self, session):
        # 爆款
        p1 = await _seed_product(
            session, name="爆款", sales_24h=12000, viewers=60000, price=99.0,
        )
        await _seed_history(session, p1.id, sales=[100, 500])
        # 低潜
        await _seed_product(
            session, name="低潜", sales_24h=10, viewers=50, price=5.0,
        )
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["hot_products"] == 1
        assert report["total"] == 2


# ── TestAverageScore ─────────────────────────────────────────


class TestAverageScore:

    @pytest.mark.anyio
    async def test_average_calculation(self, session):
        # Two products with known scores
        await _seed_product(
            session, name="A", sales_24h=10, viewers=50, price=5.0,
        )
        await _seed_product(
            session, name="B", sales_24h=10, viewers=50, price=5.0,
        )
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        # Both have same data → same score
        scores = [item["score"] for item in report["items"]]
        expected_avg = round(sum(scores) / len(scores), 1)
        assert report["average_score"] == expected_avg

    @pytest.mark.anyio
    async def test_average_score_is_float(self, session):
        await _seed_product(session, sales_24h=500, price=99.0)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert isinstance(report["average_score"], float)

    @pytest.mark.anyio
    async def test_average_zero_on_empty(self, session):
        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["average_score"] == 0.0


# ── TestReturnFields ─────────────────────────────────────────


class TestReturnFields:

    @pytest.mark.anyio
    async def test_top_level_keys(self, session):
        await _seed_product(session)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        expected_keys = {"date", "total", "hot_products", "potential_products", "average_score", "items"}
        assert set(report.keys()) == expected_keys

    @pytest.mark.anyio
    async def test_item_keys(self, session):
        await _seed_product(session, image="https://img.example.com/1.jpg")
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        item = report["items"][0]
        expected_keys = {
            "rank", "product_id", "name", "platform",
            "image", "price", "recommend_score", "knowledge_score", "final_score",
            "score", "level",
            "reasons", "lifecycle", "action", "confidence", "decision",
            "competition_score", "market_level",
        }
        assert set(item.keys()) == expected_keys

    @pytest.mark.anyio
    async def test_image_field(self, session):
        await _seed_product(session, image="https://img.example.com/product.jpg")
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["items"][0]["image"] == "https://img.example.com/product.jpg"

    @pytest.mark.anyio
    async def test_image_default_empty_string(self, session):
        await _seed_product(session, image=None)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert report["items"][0]["image"] == ""

    @pytest.mark.anyio
    async def test_reasons_is_list(self, session):
        await _seed_product(session)
        await session.commit()

        svc = DailyReportService(session)
        report = await svc.generate()

        assert isinstance(report["items"][0]["reasons"], list)
        assert len(report["items"][0]["reasons"]) >= 4
