"""Tests for CompetitionAnalyzer — price/sales/market scoring, signals, market level."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.product import Product
from app.services.competition.analyzer import CompetitionAnalyzer

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


def _product(name: str, platform: str, price: float, sales: int, category: str | None = "数码") -> Product:
    return Product(
        name=name,
        platform=platform,
        shop="测试店铺",
        price=price,
        sales_24h=sales,
        viewers=100,
        category=category,
    )


# ── Price scoring ─────────────────────────────────────────


class TestPriceScoring:
    """价格优势评分。"""

    @pytest.mark.anyio
    async def test_price_well_below_avg(self, session):
        """价格低于市场平均 20% 以上 → 30 分。"""
        # 添加同分类商品，平均价格 100
        session.add(_product("A", "xhs", 100.0, 50, "数码"))
        session.add(_product("B", "xhs", 100.0, 50, "数码"))
        # 目标商品价格 70 (低于平均 30%)
        target = _product("C", "xhs", 70.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        # 价格得分应为 30
        assert result["competition_score"] >= 30

    @pytest.mark.anyio
    async def test_price_slightly_below_avg(self, session):
        """价格低于平均但不足 20% → 20 分。"""
        session.add(_product("A", "xhs", 100.0, 50, "数码"))
        session.add(_product("B", "xhs", 100.0, 50, "数码"))
        target = _product("C", "xhs", 85.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert result["competition_score"] >= 20

    @pytest.mark.anyio
    async def test_price_above_avg(self, session):
        """价格高于平均 → 10 分。"""
        session.add(_product("A", "xhs", 80.0, 50, "数码"))
        session.add(_product("B", "xhs", 80.0, 50, "数码"))
        target = _product("C", "xhs", 120.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        # 价格分只有 10
        assert result["competition_score"] >= 10


# ── Sales scoring ─────────────────────────────────────────


class TestSalesScoring:
    """销量优势评分。"""

    @pytest.mark.anyio
    async def test_sales_above_avg(self, session):
        """销量超过平均 → 30 分。"""
        session.add(_product("A", "xhs", 100.0, 50, "数码"))
        session.add(_product("B", "xhs", 100.0, 50, "数码"))
        target = _product("C", "xhs", 100.0, 200, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        # 销量超过平均
        assert "销量超过市场平均" in result["signals"]

    @pytest.mark.anyio
    async def test_sales_near_avg(self, session):
        """销量接近平均（80%-100%）→ 20 分。"""
        session.add(_product("A", "xhs", 100.0, 100, "数码"))
        target = _product("B", "xhs", 100.0, 90, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert "销量接近市场平均" in result["signals"]

    @pytest.mark.anyio
    async def test_sales_below_avg(self, session):
        """销量低于平均 → 10 分。"""
        session.add(_product("A", "xhs", 100.0, 200, "数码"))
        target = _product("B", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        # 销量分只有 10，不应有销量优势信号
        assert "销量超过市场平均" not in result["signals"]
        assert "销量接近市场平均" not in result["signals"]


# ── Market competition scoring ────────────────────────────


class TestMarketCompetition:
    """市场竞争度评分。"""

    @pytest.mark.anyio
    async def test_few_competitors(self, session):
        """同分类商品 ≤5 → 40 分。"""
        for i in range(3):
            session.add(_product(f"商品{i}", "xhs", 100.0, 50, "数码"))
        await session.commit()

        target = _product("目标", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert "竞争商品较少" in result["signals"]

    @pytest.mark.anyio
    async def test_medium_competitors(self, session):
        """同分类商品 6-15 → 25 分。"""
        for i in range(10):
            session.add(_product(f"商品{i}", "xhs", 100.0, 50, "数码"))
        await session.commit()

        target = _product("目标", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert "市场竞争适中" in result["signals"]

    @pytest.mark.anyio
    async def test_many_competitors(self, session):
        """同分类商品 >15 → 10 分。"""
        for i in range(20):
            session.add(_product(f"商品{i}", "xhs", 100.0, 50, "数码"))
        await session.commit()

        target = _product("目标", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert "市场竞争激烈" in result["signals"]


# ── Market level ──────────────────────────────────────────


class TestMarketLevel:
    """市场等级判断。"""

    def test_low_competition(self):
        """score >= 80 → LOW。"""
        assert CompetitionAnalyzer._determine_market_level(85) == "LOW"
        assert CompetitionAnalyzer._determine_market_level(80) == "LOW"
        assert CompetitionAnalyzer._determine_market_level(100) == "LOW"

    def test_medium_competition(self):
        """50 <= score < 80 → MEDIUM。"""
        assert CompetitionAnalyzer._determine_market_level(50) == "MEDIUM"
        assert CompetitionAnalyzer._determine_market_level(79) == "MEDIUM"
        assert CompetitionAnalyzer._determine_market_level(65) == "MEDIUM"

    def test_high_competition(self):
        """score < 50 → HIGH。"""
        assert CompetitionAnalyzer._determine_market_level(49) == "HIGH"
        assert CompetitionAnalyzer._determine_market_level(0) == "HIGH"
        assert CompetitionAnalyzer._determine_market_level(30) == "HIGH"


# ── Edge cases ────────────────────────────────────────────


class TestEdgeCases:
    """边界条件。"""

    @pytest.mark.anyio
    async def test_nonexistent_product(self, session):
        """不存在的商品应返回默认值。"""
        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(9999)
        assert result["product_id"] == 9999
        assert result["competition_score"] == 0
        assert result["market_level"] == "HIGH"
        assert "商品不存在" in result["signals"]

    @pytest.mark.anyio
    async def test_no_category(self, session):
        """商品无分类时与全部商品比较。"""
        target = _product("无分类", "xhs", 100.0, 50, None)
        session.add(target)
        session.add(_product("有分类", "xhs", 80.0, 100, "数码"))
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert result["product_id"] == target.id
        assert "competition_score" in result

    @pytest.mark.anyio
    async def test_empty_db_single_product(self, session):
        """数据库中只有一个商品时的表现。"""
        target = _product("独苗", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert result["product_id"] == target.id
        assert 0 <= result["competition_score"] <= 100
        assert result["market_level"] in ("LOW", "MEDIUM", "HIGH")

    @pytest.mark.anyio
    async def test_signals_is_list(self, session):
        """signals 应为列表类型。"""
        target = _product("测试", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        assert isinstance(result["signals"], list)

    @pytest.mark.anyio
    async def test_result_keys(self, session):
        """返回值应包含指定 key。"""
        target = _product("测试", "xhs", 100.0, 50, "数码")
        session.add(target)
        await session.commit()
        await session.refresh(target)

        analyzer = CompetitionAnalyzer(session)
        result = await analyzer.analyze(target.id)
        expected_keys = {"product_id", "competition_score", "market_level", "signals"}
        assert set(result.keys()) == expected_keys
