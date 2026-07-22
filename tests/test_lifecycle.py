"""Tests for LifecycleAnalyzer — stage detection, signals, empty history."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.lifecycle.analyzer import LifecycleAnalyzer


def _h(days_ago: int, sales: int = 100, viewers: int = 1000, ai_score: float | None = None) -> SimpleNamespace:
    """Create a fake ProductHistory-like object."""
    return SimpleNamespace(
        product_id=1,
        price=99.0,
        sales_24h=sales,
        viewers=viewers,
        ai_score=ai_score,
        record_time=datetime.utcnow() - timedelta(days=days_ago),
    )


# ── NEW stage ────────────────────────────────────────────────


class TestLifecycleNew:
    """新品判断：空历史、少量记录、首次出现<7天。"""

    def test_empty_history(self):
        """空历史 → NEW。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        stage, signals = analyzer._determine_stage([])
        assert stage == "NEW"
        assert "新品出现" in signals

    def test_single_record(self):
        """只有1条记录 → NEW（≤2条）。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        stage, signals = analyzer._determine_stage([_h(days_ago=10, sales=500)])
        assert stage == "NEW"

    def test_two_records(self):
        """只有2条记录 → NEW（≤2条）。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=100),
            _h(days_ago=5, sales=200),
        ]
        stage, _ = analyzer._determine_stage(history)
        assert stage == "NEW"

    def test_three_records_but_recent_first_appearance(self):
        """3条记录但首次出现<7天 → NEW。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=3, sales=100),
            _h(days_ago=2, sales=200),
            _h(days_ago=1, sales=300),
        ]
        stage, _ = analyzer._determine_stage(history)
        assert stage == "NEW"


# ── RISING stage ─────────────────────────────────────────────


class TestLifecycleRising:
    """上涨判断：销量/浏览增长>30%。"""

    def test_sales_growth_over_30(self):
        """销量从200涨到500（+150%），不满足HOT条件 → RISING。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=200, viewers=500),
            _h(days_ago=8, sales=250, viewers=550),
            _h(days_ago=5, sales=350, viewers=600),
            _h(days_ago=2, sales=500, viewers=700),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "RISING"
        assert any("销量" in s for s in signals)

    def test_viewers_growth_over_30(self):
        """浏览量从500涨到2000（+300%），销量不变 → RISING。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=100, viewers=500),
            _h(days_ago=8, sales=100, viewers=800),
            _h(days_ago=5, sales=100, viewers=1500),
            _h(days_ago=2, sales=100, viewers=2000),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "RISING"
        assert any("浏览" in s for s in signals)


# ── HOT stage ────────────────────────────────────────────────


class TestLifecycleHot:
    """爆款判断：3+条记录、稳步增长、评分≥80。"""

    def test_hot_steady_growth_high_score(self):
        """稳步增长 + 高销量/浏览/AI分 → HOT。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=5000, viewers=10000, ai_score=80),
            _h(days_ago=8, sales=6000, viewers=12000, ai_score=85),
            _h(days_ago=5, sales=8000, viewers=15000, ai_score=90),
            _h(days_ago=2, sales=10000, viewers=20000, ai_score=95),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "HOT"
        assert any("热门" in s for s in signals)

    def test_not_hot_if_steady_but_low_score(self):
        """稳步增长但评分<80 → 不满足HOT，回退到其他阶段。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=50, viewers=200, ai_score=10),
            _h(days_ago=8, sales=60, viewers=250, ai_score=10),
            _h(days_ago=5, sales=70, viewers=300, ai_score=10),
            _h(days_ago=2, sales=80, viewers=350, ai_score=10),
        ]
        stage, _ = analyzer._determine_stage(history)
        assert stage != "HOT"

    def test_not_hot_if_unsteady_growth(self):
        """有3+条记录且高评分，但销量有波动（非稳步增长） → 不满足HOT。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=5000, viewers=10000, ai_score=90),
            _h(days_ago=8, sales=3000, viewers=12000, ai_score=90),  # sales dip
            _h(days_ago=5, sales=8000, viewers=15000, ai_score=90),
            _h(days_ago=2, sales=10000, viewers=20000, ai_score=95),
        ]
        stage, _ = analyzer._determine_stage(history)
        assert stage != "HOT"


# ── DECLINE stage ────────────────────────────────────────────


class TestLifecycleDecline:
    """衰退判断：销量/浏览下降>30%。"""

    def test_sales_decline_over_30(self):
        """销量从1000跌到500（-50%） → DECLINE。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=1000, viewers=5000),
            _h(days_ago=8, sales=800, viewers=4800),
            _h(days_ago=5, sales=600, viewers=4500),
            _h(days_ago=2, sales=500, viewers=4200),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "DECLINE"
        assert any("销量" in s for s in signals)

    def test_viewers_decline_over_30(self):
        """浏览量从10000跌到5000（-50%），销量不变 → DECLINE。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=100, viewers=10000),
            _h(days_ago=8, sales=100, viewers=8000),
            _h(days_ago=5, sales=100, viewers=6000),
            _h(days_ago=2, sales=100, viewers=5000),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "DECLINE"
        assert any("热度" in s for s in signals)

    def test_both_decline(self):
        """销量和浏览量同时下降>30% → DECLINE，两个信号都有。"""
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=1000, viewers=10000),
            _h(days_ago=8, sales=700, viewers=7000),
            _h(days_ago=5, sales=400, viewers=4000),
            _h(days_ago=2, sales=200, viewers=2000),
        ]
        stage, signals = analyzer._determine_stage(history)
        assert stage == "DECLINE"
        assert len(signals) == 2


# ── Signal generation ────────────────────────────────────────


class TestLifecycleSignals:
    """信号生成：不同阶段返回正确的信号列表。"""

    def test_new_signal(self):
        analyzer = LifecycleAnalyzer(MagicMock())
        _, signals = analyzer._determine_stage([])
        assert signals == ["新品出现"]

    def test_decline_signals(self):
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=1000, viewers=10000),
            _h(days_ago=8, sales=700, viewers=7000),
            _h(days_ago=5, sales=400, viewers=4000),
            _h(days_ago=2, sales=200, viewers=2000),
        ]
        _, signals = analyzer._determine_stage(history)
        assert "销量下降" in signals
        assert "热度降低" in signals

    def test_rising_signals(self):
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=200, viewers=500),
            _h(days_ago=8, sales=250, viewers=550),
            _h(days_ago=5, sales=350, viewers=600),
            _h(days_ago=2, sales=500, viewers=700),
        ]
        _, signals = analyzer._determine_stage(history)
        assert len(signals) >= 1

    def test_hot_signals(self):
        analyzer = LifecycleAnalyzer(MagicMock())
        history = [
            _h(days_ago=10, sales=5000, viewers=10000, ai_score=80),
            _h(days_ago=8, sales=6000, viewers=12000, ai_score=85),
            _h(days_ago=5, sales=8000, viewers=15000, ai_score=90),
            _h(days_ago=2, sales=10000, viewers=20000, ai_score=95),
        ]
        _, signals = analyzer._determine_stage(history)
        assert "持续热门" in signals
        assert "高评分" in signals


# ── analyze() integration ────────────────────────────────────


class TestLifecycleAnalyze:
    """analyze() 异步方法集成测试。"""

    @pytest.mark.anyio
    async def test_analyze_returns_correct_structure(self):
        """analyze() 返回包含 product_id/stage/score/signals 的字典。"""
        mock_session = MagicMock()
        mock_product = MagicMock(lifecycle_stage="NEW")
        mock_session.get = AsyncMock(return_value=mock_product)
        analyzer = LifecycleAnalyzer(mock_session)

        mock_history = [
            _h(days_ago=1, sales=100, viewers=500),
        ]
        with patch.object(analyzer._history_repo, "get_history", new_callable=AsyncMock, return_value=mock_history):
            result = await analyzer.analyze(product_id=42)

        assert result["product_id"] == 42
        assert result["stage"] in ("NEW", "RISING", "HOT", "DECLINE")
        assert isinstance(result["score"], int)
        assert isinstance(result["signals"], list)

    @pytest.mark.anyio
    async def test_analyze_empty_history(self):
        """空历史 → NEW，score=0。"""
        mock_session = MagicMock()
        mock_product = MagicMock(lifecycle_stage="NEW")
        mock_session.get = AsyncMock(return_value=mock_product)
        analyzer = LifecycleAnalyzer(mock_session)

        with patch.object(analyzer._history_repo, "get_history", new_callable=AsyncMock, return_value=[]):
            result = await analyzer.analyze(product_id=99)

        assert result["stage"] == "NEW"
        assert result["score"] == 0
        assert result["signals"] == ["新品出现"]


# ── Helper methods ───────────────────────────────────────────


class TestLifecycleHelpers:
    """_calculate_growth_rate / _is_steady_growth / _estimate_score 辅助方法。"""

    def test_growth_rate_zero_old(self):
        assert LifecycleAnalyzer._calculate_growth_rate(0, 100) == 100.0

    def test_growth_rate_zero_both(self):
        assert LifecycleAnalyzer._calculate_growth_rate(0, 0) == 0.0

    def test_growth_rate_positive(self):
        rate = LifecycleAnalyzer._calculate_growth_rate(100, 200)
        assert rate == pytest.approx(100.0)

    def test_growth_rate_negative(self):
        rate = LifecycleAnalyzer._calculate_growth_rate(200, 100)
        assert rate == pytest.approx(-50.0)

    def test_steady_growth_true(self):
        history = [_h(10, sales=100), _h(8, sales=200), _h(5, sales=300)]
        assert LifecycleAnalyzer._is_steady_growth(history) is True

    def test_steady_growth_false(self):
        history = [_h(10, sales=300), _h(8, sales=200), _h(5, sales=100)]
        assert LifecycleAnalyzer._is_steady_growth(history) is False

    def test_steady_growth_equal(self):
        history = [_h(10, sales=100), _h(8, sales=100), _h(5, sales=100)]
        assert LifecycleAnalyzer._is_steady_growth(history) is True

    def test_estimate_score_empty(self):
        assert LifecycleAnalyzer._estimate_score([]) == 0.0

    def test_estimate_score_high(self):
        history = [_h(1, sales=10000, viewers=20000, ai_score=90)]
        score = LifecycleAnalyzer._estimate_score(history)
        assert score >= 80

    def test_estimate_score_low(self):
        history = [_h(1, sales=10, viewers=50, ai_score=None)]
        score = LifecycleAnalyzer._estimate_score(history)
        assert score < 30
