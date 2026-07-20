"""Product ranking service — composite scoring and leaderboard."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.scoring.product_scorer import ProductScorer

# ── Scoring weights (legacy mode) ────────────────────────────

_WEIGHT_AI = 0.6
_WEIGHT_TREND = 0.4

# ── Default limit ─────────────────────────────────────────────

_DEFAULT_LIMIT = 100

# ── Level labels ──────────────────────────────────────────────

_LEVEL_HOT = "爆款"        # final_score >= 90
_LEVEL_POTENTIAL = "潜力"  # 70–90
_LEVEL_NORMAL = "一般"     # 50–70
_LEVEL_LOW = "低潜"        # < 50


class RankingService:
    """商品排行榜服务。

    支持两种模式：

    **Scorer 模式** (推荐)::

        items = [{"product": Product, "history": [ProductHistory, ...]}, ...]
        # 使用 ProductScorer 计算综合评分，按 score 降序排列。

    **Legacy 模式** (兼容)::

        items = [{"product": Product, "ai_score": float, "trend_score": float}, ...]
        # 使用 ai_score × 0.6 + trend_score × 0.4 公式。
    """

    def __init__(self) -> None:
        self._scorer = ProductScorer()

    # ── Public API ────────────────────────────────────────────

    def get_top_products(
        self,
        items: list[dict[str, Any]],
        limit: int = _DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        """生成商品排行榜。

        Args:
            items: 商品数据列表。
            limit: 返回的最大商品数量，默认 TOP 100。

        Returns:
            按分数降序排列的排行榜列表。
        """
        if not items:
            return []

        # Detect mode: if first item has "history" key → scorer mode
        if "history" in items[0]:
            return self._rank_with_scorer(items, limit)
        return self._rank_legacy(items, limit)

    # ── Scorer mode ──────────────────────────────────────────

    def _rank_with_scorer(
        self,
        items: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Rank using ProductScorer."""
        scored: list[dict[str, Any]] = []
        for item in items:
            product = item["product"]
            history = item.get("history")
            result = self._scorer.calculate_score(product, history)

            scored.append({
                "product_id": product.id,
                "name": product.name,
                "platform": product.platform,
                "price": product.price,
                "score": result["score"],
                "level": result["level"],
                "reasons": result["reasons"],
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        board: list[dict[str, Any]] = []
        for i, entry in enumerate(scored[:limit], start=1):
            entry["rank"] = i
            board.append(entry)

        logger.debug("RankingService(scorer): {} items → top {}", len(items), len(board))
        return board

    # ── Legacy mode ──────────────────────────────────────────

    def _rank_legacy(
        self,
        items: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Rank using legacy ai_score / trend_score formula."""
        scored: list[dict[str, Any]] = []
        for item in items:
            product = item["product"]
            ai = item.get("ai_score", 0.0) or 0.0
            trend = item.get("trend_score", 0.0) or 0.0
            final = round(ai * _WEIGHT_AI + trend * _WEIGHT_TREND, 2)

            scored.append({
                "product_id": product.id,
                "name": product.name,
                "platform": product.platform,
                "price": product.price,
                "ai_score": ai,
                "trend_score": trend,
                "final_score": final,
                "level": self._determine_level(final),
            })

        scored.sort(key=lambda x: x["final_score"], reverse=True)

        board: list[dict[str, Any]] = []
        for i, entry in enumerate(scored[:limit], start=1):
            entry["rank"] = i
            board.append(entry)

        logger.debug("RankingService(legacy): {} items → top {}", len(items), len(board))
        return board

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _determine_level(score: float) -> str:
        if score >= 90:
            return _LEVEL_HOT
        if score >= 70:
            return _LEVEL_POTENTIAL
        if score >= 50:
            return _LEVEL_NORMAL
        return _LEVEL_LOW
