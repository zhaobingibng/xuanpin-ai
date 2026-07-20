"""Tests for KnowledgeBuilder — auto-generate tags from review feedback."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.knowledge_repository import KnowledgeRepository
from app.database.review_repository import ReviewRepository
from app.models.recommendation_review import RecommendationReview
from app.services.knowledge.builder import KnowledgeBuilder

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


async def _seed_review(
    session: AsyncSession,
    product_id: int,
    result: str,
    sales_change: float = 10.0,
    trend_change: float = 5.0,
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


# ── learn_from_reviews ───────────────────────────────────────


class TestLearnFromReviews:
    """学习流程测试。"""

    @pytest.mark.anyio
    async def test_no_reviews(self, session):
        """无复盘记录时跳过学习。"""
        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["processed"] == 0
        assert result["success_tags"] == 0
        assert result["fail_tags"] == 0
        assert result["bindings"] == 0

    @pytest.mark.anyio
    async def test_success_high_growth(self, session):
        """SUCCESS + sales_change >= 50 → 生成 "高速增长商品" 标签。"""
        await _seed_review(session, product_id=1, result="SUCCESS", sales_change=60.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["processed"] == 1
        assert result["success_tags"] == 1
        assert result["bindings"] == 1

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(1)
        assert len(tags) == 1
        assert tags[0]["name"] == "高速增长商品"
        assert tags[0]["type"] == "SUCCESS_PATTERN"

    @pytest.mark.anyio
    async def test_success_steady_growth(self, session):
        """SUCCESS + sales_change < 50 → 生成 "稳定增长商品" 标签。"""
        await _seed_review(session, product_id=2, result="SUCCESS", sales_change=35.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["success_tags"] == 1

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(2)
        assert tags[0]["name"] == "稳定增长商品"

    @pytest.mark.anyio
    async def test_failed_sales_drop(self, session):
        """FAILED + sales_change <= -30 → 生成 "红海风险商品" 标签。"""
        await _seed_review(session, product_id=3, result="FAILED", sales_change=-40.0, trend_change=-5.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["fail_tags"] == 1

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(3)
        assert tags[0]["name"] == "红海风险商品"
        assert tags[0]["type"] == "FAIL_PATTERN"

    @pytest.mark.anyio
    async def test_failed_trend_drop(self, session):
        """FAILED + trend_change <= -20 → 生成 "趋势衰减商品" 标签。"""
        await _seed_review(session, product_id=4, result="FAILED", sales_change=-10.0, trend_change=-25.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["fail_tags"] == 1

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(4)
        assert tags[0]["name"] == "趋势衰减商品"

    @pytest.mark.anyio
    async def test_failed_both_conditions(self, session):
        """FAILED + sales_change <= -30 + trend_change <= -20 → 生成两个标签。"""
        await _seed_review(session, product_id=5, result="FAILED", sales_change=-40.0, trend_change=-30.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["fail_tags"] == 2
        assert result["bindings"] == 2

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(5)
        tag_names = {t["name"] for t in tags}
        assert tag_names == {"红海风险商品", "趋势衰减商品"}

    @pytest.mark.anyio
    async def test_normal_ignored(self, session):
        """NORMAL 复盘不生成标签。"""
        await _seed_review(session, product_id=6, result="NORMAL", sales_change=10.0, trend_change=5.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["success_tags"] == 0
        assert result["fail_tags"] == 0
        assert result["bindings"] == 0

    @pytest.mark.anyio
    async def test_mixed_reviews(self, session):
        """混合复盘：SUCCESS + FAILED + NORMAL。"""
        await _seed_review(session, product_id=10, result="SUCCESS", sales_change=55.0)
        await _seed_review(session, product_id=11, result="FAILED", sales_change=-40.0, trend_change=-5.0)
        await _seed_review(session, product_id=12, result="NORMAL", sales_change=5.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["processed"] == 3
        assert result["success_tags"] == 1
        assert result["fail_tags"] == 1

    @pytest.mark.anyio
    async def test_idempotent_tags(self, session):
        """多次学习不重复创建同名标签（幂等性）。"""
        await _seed_review(session, product_id=20, result="SUCCESS", sales_change=60.0)
        await _seed_review(session, product_id=21, result="SUCCESS", sales_change=70.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
        assert result["processed"] == 2
        assert result["success_tags"] == 2  # 两次绑定

        # 标签只有一条（幂等）
        repo = KnowledgeRepository(session)
        all_tags = await repo.get_all_tags()
        success_tags = [t for t in all_tags if t.type == "SUCCESS_PATTERN"]
        assert len(success_tags) == 1  # "高速增长商品" 只创建一次

    @pytest.mark.anyio
    async def test_bindings_committed(self, session):
        """学习后绑定应持久化到数据库。"""
        await _seed_review(session, product_id=30, result="SUCCESS", sales_change=80.0)
        await session.commit()

        builder = KnowledgeBuilder(session)
        await builder.learn_from_reviews()

        repo = KnowledgeRepository(session)
        tags = await repo.get_product_tags(30)
        assert len(tags) == 1
        assert tags[0]["source"] == "LEARNING"
        assert tags[0]["confidence"] == 1.0


# ── Analysis helpers ─────────────────────────────────────────


class TestAnalyzeHelpers:
    """_analyze_success / _analyze_failure 静态方法。"""

    def setup_method(self):
        # builder instance for calling instance methods
        self.builder = KnowledgeBuilder.__new__(KnowledgeBuilder)

    def test_analyze_success_high_growth(self):
        review = MagicMock(sales_change=60.0)
        tags = self.builder._analyze_success(review)
        assert ("高速增长商品", KnowledgeBuilder._SUCCESS_TAGS["高速增长商品"]) in tags

    def test_analyze_success_steady(self):
        review = MagicMock(sales_change=35.0)
        tags = self.builder._analyze_success(review)
        assert ("稳定增长商品", KnowledgeBuilder._SUCCESS_TAGS["稳定增长商品"]) in tags

    def test_analyze_failure_sales_only(self):
        review = MagicMock(sales_change=-40.0, trend_change=-5.0)
        tags = self.builder._analyze_failure(review)
        tag_names = [t[0] for t in tags]
        assert "红海风险商品" in tag_names
        assert "趋势衰减商品" not in tag_names

    def test_analyze_failure_trend_only(self):
        review = MagicMock(sales_change=-10.0, trend_change=-25.0)
        tags = self.builder._analyze_failure(review)
        tag_names = [t[0] for t in tags]
        assert "趋势衰减商品" in tag_names
        assert "红海风险商品" not in tag_names

    def test_analyze_failure_both(self):
        review = MagicMock(sales_change=-40.0, trend_change=-30.0)
        tags = self.builder._analyze_failure(review)
        assert len(tags) == 2

    def test_analyze_failure_fallback(self):
        """FAILED 但无明显条件 → 兜底 "红海风险商品"。"""
        review = MagicMock(sales_change=-10.0, trend_change=-5.0)
        tags = self.builder._analyze_failure(review)
        assert len(tags) == 1
        assert tags[0][0] == "红海风险商品"
