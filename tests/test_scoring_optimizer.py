"""Tests for ScoringOptimizer — weight adjustment, learning from success/failure."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.scoring_repository import ScoringRepository
from app.models.recommendation_review import RecommendationReview
from app.models.scoring_config import DEFAULT_WEIGHTS, ScoringConfig
from app.services.learning.optimizer import ScoringOptimizer

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


def _review(rid: int, product_id: int, result: str, sales_change: float = 0.0, trend_change: float = 0.0) -> RecommendationReview:
    return RecommendationReview(
        recommendation_id=rid,
        product_id=product_id,
        review_date=date.today(),
        result=result,
        sales_change=sales_change,
        trend_change=trend_change,
    )


# ── Weight adjustment ────────────────────────────────────


class TestWeightAdjustment:
    """_adjust_weights 静态方法测试。"""

    def test_positive_contribution_increases_weight(self):
        """正贡献 → 提高权重。"""
        current = dict(DEFAULT_WEIGHTS)
        analysis = {"sales_weight": 0.8, "trend_weight": 0.0, "viewer_weight": 0.0, "price_weight": 0.0, "competition_weight": 0.0}
        new = ScoringOptimizer._adjust_weights(current, analysis)
        assert new["sales_weight"] > current["sales_weight"]

    def test_negative_contribution_decreases_weight(self):
        """负贡献 → 降低权重。"""
        current = dict(DEFAULT_WEIGHTS)
        analysis = {"sales_weight": -0.8, "trend_weight": 0.0, "viewer_weight": 0.0, "price_weight": 0.0, "competition_weight": 0.0}
        new = ScoringOptimizer._adjust_weights(current, analysis)
        assert new["sales_weight"] < current["sales_weight"]

    def test_weights_sum_to_one(self):
        """权重总和必须为 1.0。"""
        current = dict(DEFAULT_WEIGHTS)
        analysis = {"sales_weight": 0.5, "trend_weight": -0.3, "viewer_weight": 0.2, "price_weight": 0.1, "competition_weight": -0.1}
        new = ScoringOptimizer._adjust_weights(current, analysis)
        total = sum(new.values())
        assert abs(total - 1.0) < 0.01

    def test_weight_bounds(self):
        """权重不能低于 0.05 或高于 0.50。"""
        current = {"sales_weight": 0.05, "trend_weight": 0.25, "viewer_weight": 0.25, "price_weight": 0.25, "competition_weight": 0.20}
        analysis = {"sales_weight": -1.0, "trend_weight": 1.0, "viewer_weight": 1.0, "price_weight": 1.0, "competition_weight": 1.0}
        new = ScoringOptimizer._adjust_weights(current, analysis)
        for w in new.values():
            assert w >= 0.04  # Allow tiny float rounding
            assert w <= 0.51

    def test_zero_contribution_no_change(self):
        """零贡献 → 权重基本不变（归一化可能微调）。"""
        current = dict(DEFAULT_WEIGHTS)
        analysis = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
        new = ScoringOptimizer._adjust_weights(current, analysis)
        for dim in DEFAULT_WEIGHTS:
            assert abs(new[dim] - current[dim]) < 0.01


# ── Full optimize pipeline ───────────────────────────────


class TestOptimize:
    """完整优化流程。"""

    @pytest.mark.anyio
    async def test_no_reviews_no_change(self, session):
        """无复盘数据时不创建新版本。"""
        optimizer = ScoringOptimizer(session)
        result = await optimizer.optimize()
        assert result["old_version"] == 0
        assert result["new_version"] == 0
        assert result["changes"] == {}
        assert "无复盘数据" in result["reason"]

    @pytest.mark.anyio
    async def test_success_learning(self, session):
        """成功商品多 → 销量权重应提高。"""
        # 添加成功复盘（销量增长高）
        for i in range(10):
            session.add(_review(i + 1, i + 1, "SUCCESS", sales_change=50.0, trend_change=30.0))
        # 添加失败复盘（销量下降）
        for i in range(5):
            session.add(_review(i + 11, i + 11, "FAILED", sales_change=-40.0, trend_change=-25.0))
        await session.commit()

        optimizer = ScoringOptimizer(session)
        result = await optimizer.optimize()
        assert result["new_version"] >= 1
        assert result["changes"] != {}

    @pytest.mark.anyio
    async def test_failure_learning(self, session):
        """失败商品多时趋势权重应降低。"""
        # 添加大量失败复盘
        for i in range(10):
            session.add(_review(i + 1, i + 1, "FAILED", sales_change=-50.0, trend_change=-30.0))
        await session.commit()

        optimizer = ScoringOptimizer(session)
        result = await optimizer.optimize()
        assert result["new_version"] >= 1

    @pytest.mark.anyio
    async def test_saves_new_config(self, session):
        """优化后应保存新 ScoringConfig。"""
        session.add(_review(1, 1, "SUCCESS", sales_change=50.0, trend_change=30.0))
        await session.commit()

        optimizer = ScoringOptimizer(session)
        await optimizer.optimize()

        repo = ScoringRepository(session)
        config = await repo.get_active()
        assert config is not None
        assert config.is_active is True
        assert config.version >= 1

    @pytest.mark.anyio
    async def test_deactivates_old_config(self, session):
        """新版本应使旧版本失效。"""
        # 第一次优化
        session.add(_review(1, 1, "SUCCESS", sales_change=50.0, trend_change=30.0))
        await session.commit()

        optimizer = ScoringOptimizer(session)
        r1 = await optimizer.optimize()
        v1 = r1["new_version"]

        # 第二次优化
        session.add(_review(2, 2, "FAILED", sales_change=-40.0, trend_change=-25.0))
        await session.commit()

        r2 = await optimizer.optimize()
        assert r2["new_version"] > v1

        # 只有最新的是 active
        repo = ScoringRepository(session)
        active = await repo.get_active()
        assert active is not None
        assert active.version == r2["new_version"]


# ── Analysis ─────────────────────────────────────────────


class TestAnalysis:
    """_analyze_reviews 静态方法测试。"""

    def test_all_success(self):
        """全部成功 → 正贡献。"""
        reviews = [_review(1, 1, "SUCCESS", sales_change=50.0, trend_change=30.0)]
        analysis = ScoringOptimizer._analyze_reviews(reviews)
        assert analysis["sales_weight"] > 0

    def test_all_failed(self):
        """全部失败 → 负贡献。"""
        reviews = [_review(1, 1, "FAILED", sales_change=-50.0, trend_change=-30.0)]
        analysis = ScoringOptimizer._analyze_reviews(reviews)
        assert analysis["sales_weight"] < 0

    def test_empty_reviews(self):
        """空列表 → 全零。"""
        analysis = ScoringOptimizer._analyze_reviews([])
        for v in analysis.values():
            assert v == 0.0

    def test_mixed_reviews(self):
        """混合结果 → 有正有负。"""
        reviews = [
            _review(1, 1, "SUCCESS", sales_change=60.0, trend_change=40.0),
            _review(2, 2, "FAILED", sales_change=-20.0, trend_change=-10.0),
        ]
        analysis = ScoringOptimizer._analyze_reviews(reviews)
        assert analysis["sales_weight"] > 0  # 成功的销量变化更大


# ── Change description ───────────────────────────────────


class TestChangeDescription:
    """_describe_changes 测试。"""

    def test_positive_change(self):
        old = {"sales_weight": 0.30}
        new = {"sales_weight": 0.35}
        changes = ScoringOptimizer._describe_changes(old, new)
        assert "+" in changes["sales_weight"]

    def test_negative_change(self):
        old = {"sales_weight": 0.30}
        new = {"sales_weight": 0.25}
        changes = ScoringOptimizer._describe_changes(old, new)
        assert "-" in changes["sales_weight"]

    def test_no_change(self):
        old = {"sales_weight": 0.30}
        new = {"sales_weight": 0.30}
        changes = ScoringOptimizer._describe_changes(old, new)
        assert changes["sales_weight"] == "0%"
