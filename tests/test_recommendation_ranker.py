"""Tests for RecommendationRanker — formula, lifecycle weighting, action sorting, edge cases."""

from __future__ import annotations

import pytest

from app.services.recommendation.ranker import RecommendationRanker


@pytest.fixture
def ranker() -> RecommendationRanker:
    return RecommendationRanker()


def _item(
    product_id: int = 1,
    name: str = "商品",
    score: int = 70,
    lifecycle: str = "NEW",
    action: str = "WATCH",
    confidence: int = 50,
    trend_score: float = 50.0,
) -> dict:
    return {
        "product_id": product_id,
        "name": name,
        "platform": "xiaohongshu",
        "image": "",
        "price": 99.0,
        "score": score,
        "level": "潜力",
        "lifecycle": lifecycle,
        "decision": {"action": action, "confidence": confidence, "reason": []},
        "trend_score": trend_score,
        "reasons": [],
    }


# ── Formula computation ──────────────────────────────────────


class TestFormulaComputation:
    """公式计算：recommend_score = score×0.5 + trend×0.25 + lifecycle×0.25。"""

    def test_basic_formula(self, ranker):
        """score=80, trend=60, lifecycle=NEW(60) → 80*0.5+60*0.25+60*0.25 = 70.0"""
        items = [_item(score=80, lifecycle="NEW", trend_score=60)]
        ranked = ranker.rank(items)
        assert ranked[0]["recommend_score"] == 70.0

    def test_all_max(self, ranker):
        """score=100, trend=100, lifecycle=HOT(100) → 100.0"""
        items = [_item(score=100, lifecycle="HOT", trend_score=100)]
        ranked = ranker.rank(items)
        assert ranked[0]["recommend_score"] == 100.0

    def test_all_zero(self, ranker):
        """score=0, trend=0, lifecycle=DECLINE(20) → 0*0.5+0*0.25+20*0.25 = 5.0"""
        items = [_item(score=0, lifecycle="DECLINE", trend_score=0)]
        ranked = ranker.rank(items)
        assert ranked[0]["recommend_score"] == 5.0

    def test_default_trend_when_missing(self, ranker):
        """无 trend_score 字段时使用默认值 50。"""
        item = _item(score=80, lifecycle="HOT")
        del item["trend_score"]
        ranked = ranker.rank([item])
        # 80*0.5 + 50*0.25 + 100*0.25 = 40 + 12.5 + 25 = 77.5
        assert ranked[0]["recommend_score"] == 77.5


# ── HOT weighting ────────────────────────────────────────────


class TestHotWeighting:
    """HOT 加权：HOT 生命周期获得最高分值 100。"""

    def test_hot_beats_new_same_score(self, ranker):
        """相同 score 和 trend，HOT 的 recommend_score 高于 NEW。"""
        hot_item = _item(product_id=1, score=80, lifecycle="HOT", trend_score=60)
        new_item = _item(product_id=2, score=80, lifecycle="NEW", trend_score=60)
        ranked = ranker.rank([new_item, hot_item])
        hot_rs = next(r["recommend_score"] for r in ranked if r["product_id"] == 1)
        new_rs = next(r["recommend_score"] for r in ranked if r["product_id"] == 2)
        assert hot_rs > new_rs

    def test_hot_value_is_100(self, ranker):
        """HOT lifecycle_value = 100 → score=60, trend=60, HOT: 60*0.5+60*0.25+100*0.25=70.0"""
        items = [_item(score=60, lifecycle="HOT", trend_score=60)]
        ranked = ranker.rank(items)
        assert ranked[0]["recommend_score"] == 70.0


# ── RISING sorting ───────────────────────────────────────────


class TestRisingSorting:
    """RISING 排序：RISING(85) 在 NEW(60) 之前。"""

    def test_rising_beats_new(self, ranker):
        """相同 score，RISING 的 recommend_score 高于 NEW。"""
        rising = _item(product_id=1, score=70, lifecycle="RISING", trend_score=50)
        new = _item(product_id=2, score=70, lifecycle="NEW", trend_score=50)
        ranked = ranker.rank([new, rising])
        assert ranked[0]["product_id"] == 1  # RISING first
        assert ranked[0]["lifecycle"] == "RISING"

    def test_rising_value_is_85(self, ranker):
        """RISING lifecycle_value = 85 → score=60, trend=60: 60*0.5+60*0.25+85*0.25=66.25 → 66.2"""
        items = [_item(score=60, lifecycle="RISING", trend_score=60)]
        ranked = ranker.rank(items)
        assert ranked[0]["recommend_score"] == 66.2


# ── Action sorting ───────────────────────────────────────────


class TestActionSorting:
    """action 排序：recommend_score 相同时按 SELL > TEST > WATCH > DROP。"""

    def test_sell_before_watch_same_recommend_score(self, ranker):
        """recommend_score 相同时 SELL 排在 WATCH 前面。"""
        sell = _item(product_id=1, score=70, lifecycle="NEW", action="SELL", trend_score=50)
        watch = _item(product_id=2, score=70, lifecycle="NEW", action="WATCH", trend_score=50)
        ranked = ranker.rank([watch, sell])
        assert ranked[0]["action"] == "SELL"
        assert ranked[1]["action"] == "WATCH"

    def test_action_priority_order(self, ranker):
        """四个 action 在 recommend_score 相同时按 SELL>TEST>WATCH>DROP 排列。"""
        items = [
            _item(product_id=1, score=70, lifecycle="NEW", action="DROP", trend_score=50),
            _item(product_id=2, score=70, lifecycle="NEW", action="SELL", trend_score=50),
            _item(product_id=3, score=70, lifecycle="NEW", action="WATCH", trend_score=50),
            _item(product_id=4, score=70, lifecycle="NEW", action="TEST", trend_score=50),
        ]
        ranked = ranker.rank(items)
        actions = [r["action"] for r in ranked]
        assert actions == ["SELL", "TEST", "WATCH", "DROP"]

    def test_recommend_score_overrides_action(self, ranker):
        """recommend_score 更高时，即使 action 优先级低也排前面。"""
        high_drop = _item(product_id=1, score=100, lifecycle="HOT", action="DROP", trend_score=100)
        low_sell = _item(product_id=2, score=30, lifecycle="DECLINE", action="SELL", trend_score=20)
        ranked = ranker.rank([low_sell, high_drop])
        assert ranked[0]["product_id"] == 1  # higher recommend_score


# ── Empty list ───────────────────────────────────────────────


class TestEmptyList:
    """空列表处理。"""

    def test_empty_input(self, ranker):
        assert ranker.rank([]) == []

    def test_single_item(self, ranker):
        ranked = ranker.rank([_item()])
        assert len(ranked) == 1
        assert ranked[0]["rank"] == 1


# ── Field completeness ───────────────────────────────────────


class TestFieldCompleteness:
    """字段完整性验证。"""

    def test_output_fields(self, ranker):
        ranked = ranker.rank([_item()])
        expected_keys = {
            "rank", "product_id", "name", "platform", "image", "price",
            "recommend_score", "knowledge_score", "final_score",
            "score", "level", "lifecycle", "action",
            "confidence", "decision", "reasons",
            "competition_score", "market_level",
        }
        assert set(ranked[0].keys()) == expected_keys

    def test_rank_assignment(self, ranker):
        items = [
            _item(product_id=1, score=90, lifecycle="HOT", trend_score=80),
            _item(product_id=2, score=60, lifecycle="NEW", trend_score=40),
            _item(product_id=3, score=75, lifecycle="RISING", trend_score=60),
        ]
        ranked = ranker.rank(items)
        ranks = [r["rank"] for r in ranked]
        assert ranks == [1, 2, 3]

    def test_reasons_from_item(self, ranker):
        item = _item()
        item["reasons"] = ["高评分", "爆款阶段"]
        item["decision"] = {"action": "SELL", "confidence": 95, "reason": ["推荐"]}
        ranked = ranker.rank([item])
        assert ranked[0]["reasons"] == ["高评分", "爆款阶段"]
