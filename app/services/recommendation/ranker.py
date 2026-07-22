"""Recommendation ranker — fuse score + trend + lifecycle + decision into final ranking."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.config.recommendation import recommendation_settings


# ── Lifecycle stage → numeric value ──────────────────────────

_LIFECYCLE_VALUES: dict[str, float] = recommendation_settings.lifecycle_values

# ── Action → sort priority (lower = higher priority) ─────────

_ACTION_PRIORITY: dict[str, int] = {
    "SELL": 0,
    "TEST": 1,
    "WATCH": 2,
    "DROP": 3,
}


class RecommendationRanker:
    """推荐排序引擎。

    融合公式：
        recommend_score = AI评分 × 0.5 + 趋势评分 × 0.25 + 生命周期分值 × 0.25

    生命周期分值：HOT=100, RISING=85, NEW=60, DECLINE=20

    排序规则（依次）：
        1. recommend_score 降序
        2. action 优先级：SELL > TEST > WATCH > DROP
        3. score 降序

    Usage::

        ranker = RecommendationRanker()
        ranked = ranker.rank(scored_items)
    """

    # ── Public API ────────────────────────────────────────────

    def rank(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """对商品列表执行推荐排序。

        Args:
            products: 每个元素至少包含 product_id, name, platform, image,
                      price, score, lifecycle, decision, trend_score(可选),
                      reasons(可选)。

        Returns:
            按 recommend_score 排序后的列表，附加 rank 和 recommend_score 字段。
        """
        if not products:
            return []

        enriched: list[dict[str, Any]] = []
        for item in products:
            knowledge_score = self._calculate_knowledge_score(item)
            recommend_score = self._calculate_recommend_score(item)
            # 知识库加成: final = recommend + knowledge × weight
            final_score = recommend_score + knowledge_score * recommendation_settings.knowledge_weight
            final_score = round(min(100.0, max(0.0, final_score)), 1)
            decision = item.get("decision", {})
            entry = {
                "product_id": item["product_id"],
                "name": item["name"],
                "platform": item.get("platform", ""),
                "image": item.get("image", ""),
                "price": item.get("price", 0.0),
                "recommend_score": recommend_score,
                "knowledge_score": knowledge_score,
                "final_score": final_score,
                "score": item["score"],
                "level": item.get("level", ""),
                "lifecycle": item["lifecycle"],
                "competition_score": item.get("competition_score"),
                "market_level": item.get("market_level"),
                "action": decision.get("action", "WATCH"),
                "confidence": decision.get("confidence", 50),
                "decision": decision,
                "reasons": item.get("reasons", []),
            }
            enriched.append(entry)

        # 三级排序 (final_score → action → score)
        enriched.sort(
            key=lambda x: (
                -x["final_score"],
                _ACTION_PRIORITY.get(x["action"], 99),
                -x["score"],
            ),
        )

        # 分配 rank
        for i, entry in enumerate(enriched, start=1):
            entry["rank"] = i

        logger.debug("[RecommendationRanker] 排序完成: 共{}条", len(enriched))
        return enriched

    # ── Score computation ─────────────────────────────────────

    @staticmethod
    def _calculate_recommend_score(item: dict[str, Any]) -> float:
        """计算 recommend_score = score×w1 + trend×w2 + lifecycle×w3。"""
        s = recommendation_settings
        ai_score = float(item.get("score", 0))
        trend_score = float(item.get("trend_score", s.trend_score_default))
        lifecycle_value = _LIFECYCLE_VALUES.get(item.get("lifecycle", "NEW"), 60.0)

        recommend = (
            ai_score * s.ai_score_weight
            + trend_score * s.trend_score_weight
            + lifecycle_value * s.lifecycle_weight
        )
        return round(min(100.0, max(0.0, recommend)), 1)

    @staticmethod
    def _calculate_knowledge_score(item: dict[str, Any]) -> float:
        """计算 knowledge_score（知识库加成）。

        基于 knowledge_tags 列表：
          - 包含 SUCCESS_PATTERN 类型标签 → bonus
          - 包含 FAIL_PATTERN 类型标签 → penalty
          - 可叠加（多个成功标签不重复加，多个失败标签不重复减）

        Returns:
            knowledge_score 值（通常 penalty 到 bonus 之间）
        """
        s = recommendation_settings
        tags = item.get("knowledge_tags", [])
        if not tags:
            return 0.0

        has_success = any(t.get("type") == "SUCCESS_PATTERN" for t in tags)
        has_fail = any(t.get("type") == "FAIL_PATTERN" for t in tags)

        score = 0.0
        if has_success:
            score += s.knowledge_bonus
        if has_fail:
            score += s.knowledge_penalty
        return score
