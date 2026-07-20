"""Tests for RecommendationRanker knowledge_score integration."""

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
    trend_score: float = 50.0,
    knowledge_tags: list | None = None,
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
        "decision": {"action": action, "confidence": 50, "reason": []},
        "trend_score": trend_score,
        "reasons": [],
        "knowledge_tags": knowledge_tags or [],
    }


# ── knowledge_score calculation ─────────────────────────────


class TestKnowledgeScore:
    """knowledge_score 计算逻辑。"""

    def test_no_tags_zero_score(self, ranker):
        """无 knowledge_tags → knowledge_score = 0。"""
        items = [_item()]
        ranked = ranker.rank(items)
        assert ranked[0]["knowledge_score"] == 0.0

    def test_success_pattern_plus_20(self, ranker):
        """SUCCESS_PATTERN 标签 → knowledge_score = +20。"""
        tags = [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}]
        items = [_item(knowledge_tags=tags)]
        ranked = ranker.rank(items)
        assert ranked[0]["knowledge_score"] == 20.0

    def test_fail_pattern_minus_20(self, ranker):
        """FAIL_PATTERN 标签 → knowledge_score = -20。"""
        tags = [{"name": "红海风险商品", "type": "FAIL_PATTERN"}]
        items = [_item(knowledge_tags=tags)]
        ranked = ranker.rank(items)
        assert ranked[0]["knowledge_score"] == -20.0

    def test_both_patterns_cancel(self, ranker):
        """同时有 SUCCESS 和 FAIL 标签 → knowledge_score = 0。"""
        tags = [
            {"name": "高速增长商品", "type": "SUCCESS_PATTERN"},
            {"name": "红海风险商品", "type": "FAIL_PATTERN"},
        ]
        items = [_item(knowledge_tags=tags)]
        ranked = ranker.rank(items)
        assert ranked[0]["knowledge_score"] == 0.0

    def test_multiple_success_no_double_count(self, ranker):
        """多个 SUCCESS_PATTERN 标签不重复加成。"""
        tags = [
            {"name": "高速增长商品", "type": "SUCCESS_PATTERN"},
            {"name": "稳定增长商品", "type": "SUCCESS_PATTERN"},
        ]
        items = [_item(knowledge_tags=tags)]
        ranked = ranker.rank(items)
        assert ranked[0]["knowledge_score"] == 20.0  # 不叠加，仍为 +20


# ── final_score integration ─────────────────────────────────


class TestFinalScore:
    """final_score = recommend_score + knowledge_score * 0.2。"""

    def test_final_score_with_success_tag(self, ranker):
        """SUCCESS 标签: final = recommend + 20*0.2 = recommend + 4。"""
        tags = [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}]
        items = [_item(score=80, lifecycle="NEW", trend_score=60, knowledge_tags=tags)]
        ranked = ranker.rank(items)
        # recommend = 80*0.5 + 60*0.25 + 60*0.25 = 70.0
        # final = 70.0 + 20*0.2 = 74.0
        assert ranked[0]["recommend_score"] == 70.0
        assert ranked[0]["final_score"] == 74.0

    def test_final_score_with_fail_tag(self, ranker):
        """FAIL 标签: final = recommend - 20*0.2 = recommend - 4。"""
        tags = [{"name": "红海风险商品", "type": "FAIL_PATTERN"}]
        items = [_item(score=80, lifecycle="NEW", trend_score=60, knowledge_tags=tags)]
        ranked = ranker.rank(items)
        # final = 70.0 + (-20)*0.2 = 66.0
        assert ranked[0]["final_score"] == 66.0

    def test_final_score_no_tags(self, ranker):
        """无标签: final = recommend。"""
        items = [_item(score=80, lifecycle="NEW", trend_score=60)]
        ranked = ranker.rank(items)
        assert ranked[0]["final_score"] == ranked[0]["recommend_score"]

    def test_final_score_clamp_100(self, ranker):
        """final_score 不超过 100。"""
        tags = [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}]
        items = [_item(score=100, lifecycle="HOT", trend_score=100, knowledge_tags=tags)]
        ranked = ranker.rank(items)
        # recommend = 100, final = 100 + 4 = 104 → clamped to 100
        assert ranked[0]["final_score"] == 100.0

    def test_final_score_clamp_0(self, ranker):
        """final_score 不低于 0。"""
        tags = [{"name": "红海风险商品", "type": "FAIL_PATTERN"}]
        items = [_item(score=0, lifecycle="DECLINE", trend_score=0, knowledge_tags=tags)]
        ranked = ranker.rank(items)
        # recommend = 0*0.5 + 0*0.25 + 20*0.25 = 5.0
        # final = 5.0 + (-20)*0.2 = 1.0
        assert ranked[0]["final_score"] >= 0.0


# ── Sorting by final_score ──────────────────────────────────


class TestKnowledgeSorting:
    """final_score 影响排序。"""

    def test_success_tag_boosts_rank(self, ranker):
        """有 SUCCESS 标签的商品排在前面。"""
        tagged = _item(
            product_id=1, score=70, lifecycle="NEW", trend_score=50,
            knowledge_tags=[{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}],
        )
        untagged = _item(product_id=2, score=70, lifecycle="NEW", trend_score=50)
        ranked = ranker.rank([untagged, tagged])
        # tagged: final = 57.5 + 4 = 61.5
        # untagged: final = 57.5
        assert ranked[0]["product_id"] == 1

    def test_fail_tag_lowers_rank(self, ranker):
        """有 FAIL 标签的商品排在后面。"""
        failed = _item(
            product_id=1, score=70, lifecycle="NEW", trend_score=50,
            knowledge_tags=[{"name": "红海风险商品", "type": "FAIL_PATTERN"}],
        )
        normal = _item(product_id=2, score=70, lifecycle="NEW", trend_score=50)
        ranked = ranker.rank([failed, normal])
        # failed: final = 57.5 - 4 = 53.5
        # normal: final = 57.5
        assert ranked[0]["product_id"] == 2


# ── Field completeness ──────────────────────────────────────


class TestKnowledgeFields:
    """输出字段完整性。"""

    def test_output_fields_include_knowledge(self, ranker):
        ranked = ranker.rank([_item()])
        assert "knowledge_score" in ranked[0]
        assert "final_score" in ranked[0]

    def test_all_expected_keys(self, ranker):
        ranked = ranker.rank([_item()])
        expected_keys = {
            "rank", "product_id", "name", "platform", "image", "price",
            "recommend_score", "knowledge_score", "final_score",
            "score", "level", "lifecycle", "action",
            "confidence", "decision", "reasons",
            "competition_score", "market_level",
        }
        assert set(ranked[0].keys()) == expected_keys
