"""Tests for SelectionAssistant — question classification, handlers, knowledge integration."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.knowledge_repository import KnowledgeRepository
from app.database.report_repository import ReportRepository
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.models.product_tag import ProductTag
from app.models.product_tag_relation import ProductTagRelation
from app.models.recommendation_review import RecommendationReview
from app.services.assistant.assistant import SelectionAssistant

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


async def _seed_product(
    session: AsyncSession,
    name: str = "蓝牙耳机",
    price: float = 99.0,
    sales_24h: int = 500,
    viewers: int = 3000,
    ai_score: float = 85.0,
) -> Product:
    p = Product(
        name=name, platform="xiaohongshu", shop="测试店铺",
        price=price, sales_24h=sales_24h, viewers=viewers,
        ai_score=ai_score,
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_history(
    session: AsyncSession,
    product_id: int,
    sales: int = 100,
    viewers: int = 500,
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


async def _seed_report(
    session: AsyncSession,
    items: list[dict],
) -> DailyReport:
    report = DailyReport(
        report_date=date.today(),
        total=len(items),
        hot_products=1,
        potential_products=1,
        average_score=80.0,
    )
    session.add(report)
    await session.flush()

    for entry in items:
        item = DailyReportItem(
            report_id=report.id,
            product_id=entry["product_id"],
            rank=entry.get("rank", 1),
            name=entry.get("name", "商品"),
            platform="xiaohongshu",
            image="",
            price=entry.get("price", 99.0),
            score=entry.get("score", 80),
            level="潜力",
            reasons="[]",
        )
        session.add(item)
    await session.flush()
    return report


async def _seed_review(
    session: AsyncSession,
    product_id: int,
    result: str = "SUCCESS",
    sales_change: float = 50.0,
    trend_change: float = 10.0,
) -> RecommendationReview:
    review = RecommendationReview(
        recommendation_id=product_id,
        product_id=product_id,
        review_date=date.today(),
        result=result,
        sales_change=sales_change,
        trend_change=trend_change,
    )
    session.add(review)
    await session.flush()
    return review


# ── Classification ────────────────────────────────────────────


class TestClassify:
    """问题分类测试。"""

    def test_recommend_keywords(self):
        assert SelectionAssistant._classify("今天有什么推荐？") == "recommend"
        assert SelectionAssistant._classify("卖什么好") == "recommend"
        assert SelectionAssistant._classify("有什么爆款") == "recommend"

    def test_trend_keywords(self):
        assert SelectionAssistant._classify("哪些商品趋势上涨") == "trend"
        assert SelectionAssistant._classify("最近增长怎么样") == "trend"
        assert SelectionAssistant._classify("趋势分析") == "trend"

    def test_risk_keywords(self):
        assert SelectionAssistant._classify("有什么风险") == "risk"
        assert SelectionAssistant._classify("不要卖什么") == "risk"
        assert SelectionAssistant._classify("竞争大的商品") == "risk"

    def test_product_keywords(self):
        assert SelectionAssistant._classify("查询蓝牙耳机") == "product"
        assert SelectionAssistant._classify("查看商品详情") == "product"

    def test_unknown(self):
        assert SelectionAssistant._classify("天气怎么样") == "unknown"
        assert SelectionAssistant._classify("你好") == "unknown"


# ── Recommend handler ────────────────────────────────────────


class TestHandleRecommend:
    """推荐类问题处理。"""

    @pytest.mark.anyio
    async def test_recommend_with_data(self, session):
        p = await _seed_product(session, "蓝牙耳机", ai_score=95.0)
        await _seed_report(session, [{"product_id": p.id, "name": "蓝牙耳机", "score": 95, "rank": 1}])
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("有什么爆款推荐？")

        assert result["products"]
        assert "推荐" in result["answer"]
        assert result["products"][0]["name"] == "蓝牙耳机"

    @pytest.mark.anyio
    async def test_recommend_no_data(self, session):
        assistant = SelectionAssistant(session)
        result = await assistant.ask("推荐什么好")

        assert result["products"] == []
        assert "暂无" in result["answer"]

    @pytest.mark.anyio
    async def test_recommend_includes_insights(self, session):
        p = await _seed_product(session)
        await _seed_report(session, [{"product_id": p.id, "name": "蓝牙耳机", "score": 80}])
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("卖什么好")

        assert isinstance(result["insights"], list)
        assert len(result["insights"]) > 0


# ── Trend handler ─────────────────────────────────────────────


class TestHandleTrend:
    """趋势类问题处理。"""

    @pytest.mark.anyio
    async def test_trend_no_products(self, session):
        assistant = SelectionAssistant(session)
        result = await assistant.ask("哪些商品趋势在上涨")

        assert result["products"] == []
        assert "暂无" in result["answer"]

    @pytest.mark.anyio
    async def test_trend_with_rising_product(self, session):
        p = await _seed_product(session, "爆款耳机", sales_24h=1000, viewers=10000)
        # Create history with strong growth
        await _seed_history(session, p.id, sales=50, viewers=200, days_ago=10)
        await _seed_history(session, p.id, sales=200, viewers=800, days_ago=5)
        await _seed_history(session, p.id, sales=1000, viewers=10000, days_ago=1)
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("趋势分析")

        # Should find at least one trending product
        assert "趋势" in result["answer"] or "发现" in result["answer"]
        assert isinstance(result["insights"], list)

    @pytest.mark.anyio
    async def test_trend_with_insufficient_history(self, session):
        """只有1条历史记录时无法分析趋势。"""
        p = await _seed_product(session)
        await _seed_history(session, p.id, days_ago=1)
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("增长情况如何")

        assert "未发现" in result["answer"] or "趋势" in result["answer"]


# ── Risk handler ──────────────────────────────────────────────


class TestHandleRisk:
    """风险类问题处理。"""

    @pytest.mark.anyio
    async def test_risk_no_products(self, session):
        assistant = SelectionAssistant(session)
        result = await assistant.ask("有什么风险")

        assert result["products"] == []
        assert "暂无" in result["answer"]

    @pytest.mark.anyio
    async def test_risk_with_products(self, session):
        p = await _seed_product(session, "蓝牙耳机")
        await session.commit()

        assistant = SelectionAssistant(session)
        # Patch CompetitionAnalyzer to return high-risk result
        with patch(
            "app.services.assistant.assistant.CompetitionAnalyzer"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.analyze = AsyncMock(return_value={
                "product_id": p.id,
                "competition_score": 20,
                "market_level": "HIGH",
                "signals": ["同品类商品多"],
            })
            mock_cls.return_value = mock_instance

            result = await assistant.ask("竞争风险怎么样")

        assert "高风险" in result["answer"] or "谨慎" in result["answer"]
        assert len(result["products"]) >= 1


# ── Product handler ───────────────────────────────────────────


class TestHandleProduct:
    """商品查询类问题处理。"""

    @pytest.mark.anyio
    async def test_product_found(self, session):
        await _seed_product(session, "蓝牙耳机", ai_score=90.0)
        await _seed_product(session, "蓝牙音箱", ai_score=75.0)
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("查询蓝牙")

        assert "找到" in result["answer"]
        assert len(result["products"]) >= 1

    @pytest.mark.anyio
    async def test_product_not_found(self, session):
        await _seed_product(session, "蓝牙耳机")
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("查询电冰箱")

        assert "未找到" in result["answer"]
        assert result["products"] == []

    @pytest.mark.anyio
    async def test_product_empty_keyword(self, session):
        """只有关键词无实际搜索词。"""
        assistant = SelectionAssistant(session)
        result = await assistant.ask("查询")

        assert "请提供" in result["answer"]

    @pytest.mark.anyio
    async def test_product_with_knowledge_tags(self, session):
        p = await _seed_product(session, "蓝牙耳机", ai_score=90.0)
        # Add a success pattern tag
        tag = ProductTag(name="高速增长商品", type="SUCCESS_PATTERN", description="测试")
        session.add(tag)
        await session.flush()

        rel = ProductTagRelation(product_id=p.id, tag_id=tag.id, confidence=1.0, source="LEARNING")
        session.add(rel)
        await session.commit()

        assistant = SelectionAssistant(session)
        result = await assistant.ask("查询蓝牙耳机")

        assert len(result["products"]) == 1
        product = result["products"][0]
        assert "高速增长商品" in product["tags"]
        assert any("历史表现优秀" in r for r in product["reason"])


# ── Unknown handler ───────────────────────────────────────────


class TestHandleUnknown:
    """未知问题处理。"""

    def test_unknown_returns_guidance(self):
        result = SelectionAssistant._handle_unknown("今天天气怎么样")
        assert "抱歉" in result["answer"]
        assert result["products"] == []
        assert len(result["insights"]) > 0

    @pytest.mark.anyio
    async def test_ask_unknown(self, session):
        assistant = SelectionAssistant(session)
        result = await assistant.ask("你好世界")

        assert "抱歉" in result["answer"] or "暂时" in result["answer"]
        assert result["products"] == []

    @pytest.mark.anyio
    async def test_ask_empty_question(self, session):
        assistant = SelectionAssistant(session)
        result = await assistant.ask("")

        assert "请输入" in result["answer"]


# ── Knowledge integration ────────────────────────────────────


class TestKnowledgeIntegration:
    """知识库集成测试。"""

    @pytest.mark.anyio
    async def test_build_product_info_with_success_tag(self, session):
        p = await _seed_product(session)
        tag = ProductTag(name="蓝海商品", type="SUCCESS_PATTERN", description="")
        session.add(tag)
        await session.flush()

        rel = ProductTagRelation(product_id=p.id, tag_id=tag.id, confidence=1.0, source="LEARNING")
        session.add(rel)
        await session.commit()

        assistant = SelectionAssistant(session)
        info = await assistant._build_product_info(p.id, "蓝牙耳机", 85)

        assert info["name"] == "蓝牙耳机"
        assert info["score"] == 85
        assert "蓝海商品" in info["tags"]

    @pytest.mark.anyio
    async def test_build_product_info_with_fail_tag(self, session):
        p = await _seed_product(session)
        tag = ProductTag(name="红海风险商品", type="FAIL_PATTERN", description="")
        session.add(tag)
        await session.flush()

        rel = ProductTagRelation(product_id=p.id, tag_id=tag.id, confidence=1.0, source="LEARNING")
        session.add(rel)
        await session.commit()

        assistant = SelectionAssistant(session)
        info = await assistant._build_product_info(p.id, "蓝牙耳机", 50)

        assert "红海风险商品" in info["tags"]
        assert any("存在风险标签" in r for r in info["reason"])

    @pytest.mark.anyio
    async def test_build_product_info_no_tags(self, session):
        p = await _seed_product(session)
        await session.commit()

        assistant = SelectionAssistant(session)
        info = await assistant._build_product_info(p.id, "蓝牙耳机", 70)

        assert info["tags"] == []
        assert info["reason"] == []


# ── History persistence ───────────────────────────────────────


class TestHistoryPersistence:
    """问答历史持久化测试。"""

    @pytest.mark.anyio
    async def test_ask_saves_history(self, session):
        assistant = SelectionAssistant(session)
        await assistant.ask("有什么推荐")

        from app.database.assistant_repository import AssistantRepository
        repo = AssistantRepository(session)
        records = await repo.history(limit=10)
        assert len(records) == 1
        assert records[0].question == "有什么推荐"
        # answer should be valid JSON
        parsed = json.loads(records[0].answer)
        assert "answer" in parsed
        assert "products" in parsed

    @pytest.mark.anyio
    async def test_multiple_asks_save_history(self, session):
        assistant = SelectionAssistant(session)
        await assistant.ask("推荐什么")
        await assistant.ask("趋势如何")

        from app.database.assistant_repository import AssistantRepository
        repo = AssistantRepository(session)
        records = await repo.history(limit=10)
        assert len(records) == 2


# ── Extract product keyword ──────────────────────────────────


class TestExtractProductKeyword:
    """商品名称关键词提取。"""

    def test_extract_simple(self):
        assert SelectionAssistant._extract_product_keyword("查询蓝牙耳机") == "蓝牙耳机"

    def test_extract_with_multiple_prefixes(self):
        result = SelectionAssistant._extract_product_keyword("查看商品详情")
        assert result is None or result == ""

    def test_extract_empty_after_clean(self):
        result = SelectionAssistant._extract_product_keyword("查询")
        assert result is None

    def test_extract_with_question_mark(self):
        result = SelectionAssistant._extract_product_keyword("蓝牙耳机？")
        assert "蓝牙耳机" in result
