"""Tests for ProductStrategyGenerator — title, selling points, copy, price, profit."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.strategy_repository import StrategyRepository
from app.services.strategy.generator import ProductStrategyGenerator

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


def _product(
    product_id: int = 1,
    name: str = "蓝牙耳机",
    price: float = 99.0,
    sales_24h: int = 500,
    trend_score: float = 75.0,
    lifecycle: str = "HOT",
    competition_score: int = 60,
    knowledge_tags: list | None = None,
) -> dict:
    return {
        "product_id": product_id,
        "name": name,
        "price": price,
        "sales_24h": sales_24h,
        "trend_score": trend_score,
        "lifecycle": lifecycle,
        "competition_score": competition_score,
        "knowledge_tags": knowledge_tags or [],
    }


# ── Title generation ──────────────────────────────────────────


class TestTitleGeneration:
    """标题生成测试。"""

    def test_title_contains_name(self):
        title = ProductStrategyGenerator._generate_title("蓝牙耳机", ["高音质"])
        assert "蓝牙耳机" in title

    def test_title_contains_selling_point(self):
        title = ProductStrategyGenerator._generate_title("蓝牙耳机", ["主动降噪"])
        assert "主动降噪" in title

    def test_title_has_prefix(self):
        title = ProductStrategyGenerator._generate_title("蓝牙耳机", ["长续航"])
        # Should have audience prefix like "学生党必备" or similar
        prefixes = ["学生党必备", "打工人必入", "宝妈推荐", "居家好物", "潮流达人"]
        assert any(p in title for p in prefixes)

    def test_title_empty_selling_points(self):
        title = ProductStrategyGenerator._generate_title("蓝牙耳机", [])
        assert "蓝牙耳机" in title

    def test_title_deterministic(self):
        """Same input should produce same title."""
        t1 = ProductStrategyGenerator._generate_title("蓝牙耳机", ["降噪"])
        t2 = ProductStrategyGenerator._generate_title("蓝牙耳机", ["降噪"])
        assert t1 == t2


# ── Selling points ────────────────────────────────────────────


class TestSellingPoints:
    """卖点生成测试。"""

    def test_high_sales(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=1000, trend=60, lifecycle="HOT", tags=[]
        )
        assert any("爆款" in p or "热销" in p for p in points)

    def test_low_sales(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=10, trend=60, lifecycle="NEW", tags=[]
        )
        assert any("小众" in p or "精选" in p for p in points)

    def test_high_trend(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=200, trend=80, lifecycle="NEW", tags=[]
        )
        assert any("趋势上涨" in p for p in points)

    def test_hot_lifecycle(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=200, trend=50, lifecycle="HOT", tags=[]
        )
        assert any("爆款阶段" in p for p in points)

    def test_rising_lifecycle(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=200, trend=50, lifecycle="RISING", tags=[]
        )
        assert any("新锐" in p or "潜力" in p for p in points)

    def test_success_tag(self):
        tags = [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}]
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=200, trend=50, lifecycle="NEW", tags=tags
        )
        assert any("AI认证" in p for p in points)

    def test_min_three_points(self):
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=10, trend=30, lifecycle="NEW", tags=[]
        )
        assert len(points) >= 3

    def test_max_five_points(self):
        tags = [{"name": "蓝海商品", "type": "SUCCESS_PATTERN"}]
        points = ProductStrategyGenerator._generate_selling_points(
            "耳机", sales=1000, trend=80, lifecycle="HOT", tags=tags
        )
        assert len(points) <= 5


# ── Xiaohongshu copy ──────────────────────────────────────────


class TestXiaohongshuCopy:
    """小红书文案生成测试。"""

    def test_contains_product_name(self):
        copy = ProductStrategyGenerator._generate_xiaohongshu_copy(
            "蓝牙耳机", ["高音质", "长续航"], []
        )
        assert "蓝牙耳机" in copy

    def test_contains_selling_points(self):
        copy = ProductStrategyGenerator._generate_xiaohongshu_copy(
            "蓝牙耳机", ["高音质", "长续航"], []
        )
        assert "高音质" in copy
        assert "长续航" in copy

    def test_has_hashtags(self):
        copy = ProductStrategyGenerator._generate_xiaohongshu_copy(
            "蓝牙耳机", ["高音质"], []
        )
        assert "#好物推荐" in copy
        assert "#种草" in copy

    def test_has_tag_hashtags(self):
        tags = [{"name": "蓝海商品", "type": "SUCCESS_PATTERN"}]
        copy = ProductStrategyGenerator._generate_xiaohongshu_copy(
            "蓝牙耳机", ["高音质"], tags
        )
        assert "#蓝海商品" in copy


# ── Xianyu copy ───────────────────────────────────────────────


class TestXianyuCopy:
    """闲鱼文案生成测试。"""

    def test_contains_product_name(self):
        copy = ProductStrategyGenerator._generate_xianyu_copy(
            "蓝牙耳机", ["高音质", "长续航"], 99.0
        )
        assert "蓝牙耳机" in copy

    def test_contains_selling_points(self):
        copy = ProductStrategyGenerator._generate_xianyu_copy(
            "蓝牙耳机", ["高音质", "长续航"], 99.0
        )
        assert "高音质" in copy

    def test_contains_discount_price(self):
        copy = ProductStrategyGenerator._generate_xianyu_copy(
            "蓝牙耳机", ["高音质"], 100.0
        )
        assert "85" in copy  # 100 * 0.85 = 85

    def test_contains_original_price(self):
        copy = ProductStrategyGenerator._generate_xianyu_copy(
            "蓝牙耳机", ["高音质"], 100.0
        )
        assert "100" in copy


# ── Price strategy ────────────────────────────────────────────


class TestPriceStrategy:
    """价格策略生成测试。"""

    def test_cost_calculation(self):
        strategy = ProductStrategyGenerator._generate_price_strategy(100.0)
        assert strategy["cost"] == 60.0  # 100 * 0.6

    def test_sell_equals_price(self):
        strategy = ProductStrategyGenerator._generate_price_strategy(99.0)
        assert strategy["sell"] == 99.0

    def test_profit_calculation(self):
        strategy = ProductStrategyGenerator._generate_price_strategy(100.0)
        assert strategy["profit"] == 40.0  # 100 - 60

    def test_zero_price(self):
        strategy = ProductStrategyGenerator._generate_price_strategy(0.0)
        assert strategy["cost"] == 0.0
        assert strategy["profit"] == 0.0


# ── Profit analysis ───────────────────────────────────────────


class TestProfitAnalysis:
    """利润分析测试。"""

    def test_margin_calculation(self):
        price_strategy = {"cost": 60.0, "sell": 100.0, "profit": 40.0}
        analysis = ProductStrategyGenerator._generate_profit_analysis(100.0, price_strategy)
        assert analysis["profit_margin"] == "40.0%"

    def test_daily_estimate(self):
        price_strategy = {"cost": 60.0, "sell": 100.0, "profit": 40.0}
        analysis = ProductStrategyGenerator._generate_profit_analysis(100.0, price_strategy)
        assert analysis["daily_estimate"] == 400.0  # 40 * 10

    def test_monthly_estimate(self):
        price_strategy = {"cost": 60.0, "sell": 100.0, "profit": 40.0}
        analysis = ProductStrategyGenerator._generate_profit_analysis(100.0, price_strategy)
        assert analysis["monthly_estimate"] == 12000.0  # 40 * 10 * 30

    def test_zero_price_margin(self):
        price_strategy = {"cost": 0.0, "sell": 0.0, "profit": 0.0}
        analysis = ProductStrategyGenerator._generate_profit_analysis(0.0, price_strategy)
        assert analysis["profit_margin"] == "0.0%"


# ── Full generate flow ────────────────────────────────────────


class TestGenerateFlow:
    """完整生成流程测试。"""

    @pytest.mark.anyio
    async def test_generate_persists(self, session):
        generator = ProductStrategyGenerator(session)
        result = await generator.generate(_product())

        repo = StrategyRepository(session)
        saved = await repo.get_strategy(1)
        assert saved is not None
        assert saved.product_id == 1
        assert saved.title == result["title"]

    @pytest.mark.anyio
    async def test_generate_returns_all_fields(self, session):
        generator = ProductStrategyGenerator(session)
        result = await generator.generate(_product())

        assert "title" in result
        assert "selling_points" in result
        assert "xiaohongshu_copy" in result
        assert "xianyu_copy" in result
        assert "price_strategy" in result
        assert "profit_analysis" in result
        assert result["product_id"] == 1

    @pytest.mark.anyio
    async def test_generate_with_tags(self, session):
        tags = [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}]
        generator = ProductStrategyGenerator(session)
        result = await generator.generate(_product(knowledge_tags=tags))

        assert any("AI认证" in sp for sp in result["selling_points"])
