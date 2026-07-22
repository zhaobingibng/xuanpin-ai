"""Tests for Phase 14 Task 3: SupplyChainMatcher and mock data."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch
from app.services.supply_chain.matcher import SupplyChainMatcher
from app.services.supply_chain.mock_data import (
    MOCK_1688_CATALOG,
    get_1688_catalog,
    search_1688_by_keyword,
)


# ── Mock Data Tests ────────────────────────────────────────────


class TestMock1688Data:
    """Mock 1688 数据测试。"""

    def test_catalog_not_empty(self):
        """Mock 目录不为空。"""
        assert len(MOCK_1688_CATALOG) > 0

    def test_get_catalog_returns_copy(self):
        """get_1688_catalog 应返回副本。"""
        catalog = get_1688_catalog()
        assert len(catalog) == len(MOCK_1688_CATALOG)
        catalog.clear()
        assert len(MOCK_1688_CATALOG) > 0  # 原始不受影响

    def test_search_by_keyword_bluetooth(self):
        """搜索 '耳机' 应找到蓝牙耳机。"""
        results = search_1688_by_keyword("耳机")
        assert len(results) >= 2
        assert all("耳机" in r.title for r in results)

    def test_search_by_keyword_phone_case(self):
        """搜索 '手机壳' 应找到手机壳。"""
        results = search_1688_by_keyword("手机壳")
        assert len(results) >= 1

    def test_search_by_keyword_no_match(self):
        """搜索不存在的品类返回空。"""
        results = search_1688_by_keyword("火箭发动机")
        assert len(results) == 0

    def test_search_limit(self):
        """搜索结果应受 limit 限制。"""
        results = search_1688_by_keyword("", limit=3)
        assert len(results) <= 3


# ── Matcher Tests ──────────────────────────────────────────────


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


class TestSupplyChainMatcher:
    """SupplyChainMatcher 测试。"""

    @pytest.mark.anyio
    async def test_title_similarity_high(self, session):
        """高相似标题应匹配成功。"""
        product = Product(
            name="无线蓝牙耳机入耳式降噪运动超长续航",
            platform="taobao",
            shop="测试店",
            price=59.9,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        matcher = SupplyChainMatcher(session)
        match = await matcher.match_product(product)

        assert match is not None
        assert match.match_score > 0.5
        assert match.cost_price > 0
        assert match.sell_price == 59.9

    @pytest.mark.anyio
    async def test_title_similarity_no_match(self, session):
        """完全不相关的标题不应匹配。"""
        product = Product(
            name="火箭发动机涡轮叶片高温合金",
            platform="taobao",
            shop="航天店",
            price=999999.0,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        matcher = SupplyChainMatcher(session)
        match = await matcher.match_product(product)

        assert match is None

    @pytest.mark.anyio
    async def test_match_batch(self, session):
        """批量匹配应返回多个结果。"""
        products = [
            Product(name="无线蓝牙耳机降噪", platform="taobao", shop="店A", price=69.9),
            Product(name="桌面收纳盒化妆品整理", platform="taobao", shop="店B", price=29.9),
            Product(name="火箭推进器", platform="taobao", shop="店C", price=1.0),
        ]
        for p in products:
            session.add(p)
        await session.commit()
        for p in products:
            await session.refresh(p)

        matcher = SupplyChainMatcher(session)
        matches = await matcher.match_batch(products)

        # 前两个应匹配成功，第三个不应匹配
        assert len(matches) >= 2

    @pytest.mark.anyio
    async def test_match_creates_db_record(self, session):
        """匹配成功应创建数据库记录。"""
        product = Product(
            name="口红哑光雾面持久不脱色",
            platform="taobao",
            shop="美妆店",
            price=39.9,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        matcher = SupplyChainMatcher(session)
        match = await matcher.match_product(product)

        assert match is not None
        assert match.id is not None
        assert match.product_id == product.id
        assert match.status == "MATCHED"

    def test_title_similarity_empty(self):
        """空标题相似度应为 0。"""
        assert SupplyChainMatcher._title_similarity("", "test") == 0.0
        assert SupplyChainMatcher._title_similarity("test", "") == 0.0

    def test_title_similarity_identical(self):
        """相同标题相似度应为 1.0。"""
        score = SupplyChainMatcher._title_similarity("蓝牙耳机", "蓝牙耳机")
        assert score == 1.0

    def test_calculate_profit_basic(self):
        """基本利润计算。"""
        result = SupplyChainMatcher._calculate_profit(
            sell_price=100.0,
            cost_price=30.0,
            fee_rate=0.05,
            shipping=5.0,
        )
        # 100 - 30 - 5(佣金) - 5(运费) = 60
        assert result["amount"] == 60.0
        assert result["margin"] == 60.0  # 60%

    def test_calculate_profit_zero_sell(self):
        """售价为 0 时利润为 0。"""
        result = SupplyChainMatcher._calculate_profit(
            sell_price=0.0,
            cost_price=30.0,
        )
        assert result["amount"] == 0.0
        assert result["margin"] == 0.0


# ── SupplyChainMatch Model ─────────────────────────────────────


class TestSupplyChainMatchModel:
    """SupplyChainMatch ORM 模型测试。"""

    def test_model_repr(self):
        """模型 repr 应包含关键信息。"""
        match = SupplyChainMatch(
            id=1, product_id=10, match_score=0.85, profit_margin=35.0
        )
        repr_str = repr(match)
        assert "product_id=10" in repr_str
        assert "0.85" in repr_str
