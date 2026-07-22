"""Recommendation module settings — 推荐/排序/查询配置 (Phase 47.2)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecommendationSettings:
    """推荐模块配置。

    包含评分权重、生命周期映射、分页默认值等。
    """

    # ── 评分权重 ──────────────────────────────────────────
    # recommend_score = ai_score × ai_weight
    #                 + trend_score × trend_weight
    #                 + lifecycle_value × lifecycle_weight
    ai_score_weight: float = 0.5
    trend_score_weight: float = 0.25
    lifecycle_weight: float = 0.25

    # final_score = recommend_score + knowledge_score × knowledge_weight
    knowledge_weight: float = 0.2

    # 知识库标签加分/扣分
    knowledge_bonus: float = 20.0
    knowledge_penalty: float = -20.0

    # ── 生命周期分值映射 ──────────────────────────────────
    lifecycle_values: dict[str, float] = field(default_factory=lambda: {
        "HOT": 100.0,
        "RISING": 85.0,
        "NEW": 60.0,
        "DECLINE": 20.0,
    })

    # ── 默认值 ────────────────────────────────────────────
    trend_score_default: float = 50.0
    """无历史趋势数据时的默认趋势分。"""

    # ── 分页 / 数量限制 ───────────────────────────────────
    product_list_limit: int = 10_000
    """每日推荐候选商品查询上限。"""

    pool_list_limit: int = 50
    """推荐池列表默认分页大小。"""

    publish_history_limit: int = 20
    """发布历史默认返回条数。"""


# 模块级单例
recommendation_settings = RecommendationSettings()
