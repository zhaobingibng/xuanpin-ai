"""Tests for ProductDecisionEngine — SELL/TEST/WATCH/DROP + confidence + reasons."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.decision.engine import ProductDecisionEngine


@pytest.fixture
def engine() -> ProductDecisionEngine:
    return ProductDecisionEngine()


@pytest.fixture
def product() -> MagicMock:
    p = MagicMock()
    p.name = "测试商品"
    p.platform = "xiaohongshu"
    p.price = 99.0
    return p


# ── SELL ─────────────────────────────────────────────────────


class TestDecisionSell:
    """SELL 判断：score >= 90 且 lifecycle == HOT。"""

    def test_sell_high_score_hot(self, engine, product):
        result = engine.decide(product, score=95, lifecycle="HOT")
        assert result["action"] == "SELL"
        assert result["confidence"] >= 90

    def test_sell_exact_90_hot(self, engine, product):
        result = engine.decide(product, score=90, lifecycle="HOT")
        assert result["action"] == "SELL"
        assert result["confidence"] == 90

    def test_sell_perfect_score(self, engine, product):
        result = engine.decide(product, score=100, lifecycle="HOT")
        assert result["action"] == "SELL"
        assert result["confidence"] == 100

    def test_sell_reasons(self, engine, product):
        result = engine.decide(product, score=95, lifecycle="HOT")
        assert "高评分" in result["reason"]
        assert "爆款阶段" in result["reason"]

    def test_not_sell_if_not_hot(self, engine, product):
        """score=95 但 lifecycle=RISING → 不是 SELL。"""
        result = engine.decide(product, score=95, lifecycle="RISING")
        assert result["action"] != "SELL"

    def test_not_sell_if_low_score(self, engine, product):
        """score=85 + lifecycle=HOT → 不满足 score>=90。"""
        result = engine.decide(product, score=85, lifecycle="HOT")
        assert result["action"] != "SELL"


# ── TEST ─────────────────────────────────────────────────────


class TestDecisionTest:
    """TEST 判断：score >= 70 且 lifecycle == RISING。"""

    def test_test_rising_70(self, engine, product):
        result = engine.decide(product, score=70, lifecycle="RISING")
        assert result["action"] == "TEST"

    def test_test_rising_85(self, engine, product):
        result = engine.decide(product, score=85, lifecycle="RISING")
        assert result["action"] == "TEST"
        assert result["confidence"] <= 90

    def test_test_reasons(self, engine, product):
        result = engine.decide(product, score=75, lifecycle="RISING")
        assert "增长阶段" in result["reason"]
        assert "建议小批量测试" in result["reason"]

    def test_not_test_if_decline(self, engine, product):
        """score=80 + lifecycle=DECLINE → DROP（DECLINE优先）。"""
        result = engine.decide(product, score=80, lifecycle="DECLINE")
        assert result["action"] == "DROP"

    def test_not_test_if_new(self, engine, product):
        """score=75 + lifecycle=NEW → WATCH（不匹配 RISING）。"""
        result = engine.decide(product, score=75, lifecycle="NEW")
        assert result["action"] == "WATCH"


# ── WATCH ────────────────────────────────────────────────────


class TestDecisionWatch:
    """WATCH 判断：score 50-70。"""

    def test_watch_score_50(self, engine, product):
        result = engine.decide(product, score=50, lifecycle="NEW")
        assert result["action"] == "WATCH"

    def test_watch_score_60(self, engine, product):
        result = engine.decide(product, score=60, lifecycle="NEW")
        assert result["action"] == "WATCH"

    def test_watch_score_69(self, engine, product):
        result = engine.decide(product, score=69, lifecycle="NEW")
        assert result["action"] == "WATCH"

    def test_watch_reasons(self, engine, product):
        result = engine.decide(product, score=55, lifecycle="NEW")
        assert any("观察" in r for r in result["reason"])

    def test_watch_high_score_non_matching_lifecycle(self, engine, product):
        """score=80 + lifecycle=NEW → WATCH（不匹配 SELL/TEST）。"""
        result = engine.decide(product, score=80, lifecycle="NEW")
        assert result["action"] == "WATCH"

    def test_watch_confidence_range(self, engine, product):
        result = engine.decide(product, score=60, lifecycle="NEW")
        assert 30 <= result["confidence"] <= 70


# ── DROP ─────────────────────────────────────────────────────


class TestDecisionDrop:
    """DROP 判断：score < 50 或 lifecycle == DECLINE。"""

    def test_drop_low_score(self, engine, product):
        result = engine.decide(product, score=30, lifecycle="NEW")
        assert result["action"] == "DROP"

    def test_drop_score_zero(self, engine, product):
        result = engine.decide(product, score=0, lifecycle="NEW")
        assert result["action"] == "DROP"

    def test_drop_score_49(self, engine, product):
        result = engine.decide(product, score=49, lifecycle="NEW")
        assert result["action"] == "DROP"

    def test_drop_decline_any_score(self, engine, product):
        """DECLINE 阶段，即使 score 较高也 DROP。"""
        result = engine.decide(product, score=80, lifecycle="DECLINE")
        assert result["action"] == "DROP"

    def test_drop_decline_high_score(self, engine, product):
        result = engine.decide(product, score=95, lifecycle="DECLINE")
        assert result["action"] == "DROP"

    def test_drop_decline_reasons(self, engine, product):
        result = engine.decide(product, score=60, lifecycle="DECLINE")
        assert "商品衰退" in result["reason"]

    def test_drop_low_score_reasons(self, engine, product):
        result = engine.decide(product, score=30, lifecycle="NEW")
        assert any("偏低" in r for r in result["reason"])


# ── Confidence ───────────────────────────────────────────────


class TestDecisionConfidence:
    """confidence 计算验证。"""

    def test_sell_confidence_increases_with_score(self, engine, product):
        c90 = engine.decide(product, score=90, lifecycle="HOT")["confidence"]
        c95 = engine.decide(product, score=95, lifecycle="HOT")["confidence"]
        c100 = engine.decide(product, score=100, lifecycle="HOT")["confidence"]
        assert c90 <= c95 <= c100
        assert c90 == 90
        assert c95 == 95
        assert c100 == 100

    def test_test_confidence_increases_with_score(self, engine, product):
        c70 = engine.decide(product, score=70, lifecycle="RISING")["confidence"]
        c80 = engine.decide(product, score=80, lifecycle="RISING")["confidence"]
        assert c70 == 70
        assert c80 == 80
        assert c70 < c80

    def test_test_confidence_capped_at_90(self, engine, product):
        result = engine.decide(product, score=89, lifecycle="RISING")
        assert result["confidence"] == 89
        result2 = engine.decide(product, score=90, lifecycle="RISING")
        assert result2["confidence"] <= 90

    def test_drop_confidence_low_score(self, engine, product):
        """score=0 → confidence=50; score=40 → confidence=10。"""
        c0 = engine.decide(product, score=0, lifecycle="NEW")["confidence"]
        c40 = engine.decide(product, score=40, lifecycle="NEW")["confidence"]
        assert c0 == 50
        assert c40 == 10

    def test_drop_confidence_min_10(self, engine, product):
        """confidence 不低于 10。"""
        result = engine.decide(product, score=49, lifecycle="NEW")
        assert result["confidence"] >= 10


# ── Reason generation ────────────────────────────────────────


class TestDecisionReason:
    """reason 生成验证。"""

    def test_sell_reason_is_list(self, engine, product):
        result = engine.decide(product, score=95, lifecycle="HOT")
        assert isinstance(result["reason"], list)
        assert len(result["reason"]) >= 2

    def test_test_reason_is_list(self, engine, product):
        result = engine.decide(product, score=75, lifecycle="RISING")
        assert isinstance(result["reason"], list)
        assert len(result["reason"]) >= 2

    def test_watch_reason_contains_score(self, engine, product):
        result = engine.decide(product, score=55, lifecycle="NEW")
        assert any("55" in r for r in result["reason"])

    def test_drop_decline_reason_contains_decline(self, engine, product):
        result = engine.decide(product, score=60, lifecycle="DECLINE")
        assert "商品衰退" in result["reason"]
