"""Product ranking service — composite scoring and leaderboard."""

from __future__ import annotations

from typing import Any

from loguru import logger

# ── Scoring weights ────────────────────────────────────────────

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

    输入包含 product 对象 + ai_score + trend_score 的字典列表，
    按综合评分（ai_score × 0.6 + trend_score × 0.4）降序排列，
    输出带 rank / level 的排行榜。

    Usage::

        service = RankingService()
        board = service.get_top_products([
            {"product": product_obj, "ai_score": 85.0, "trend_score": 70.0},
            ...
        ])
        # [{"rank": 1, "product_id": 5, "name": "...", ...}, ...]
    """

    # ── Public API ────────────────────────────────────────────

    def get_top_products(
        self,
        items: list[dict[str, Any]],
        limit: int = _DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        """生成商品排行榜。

        Args:
            items: 每个元素为 ``{"product": Product, "ai_score": float, "trend_score": float}``。
            limit: 返回的最大商品数量，默认 TOP 100。

        Returns:
            按 final_score 降序排列的排行榜列表，每个元素包含：
            rank, product_id, name, platform, price,
            ai_score, trend_score, final_score, level。
        """
        if not items:
            return []

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

        # Sort descending by final_score
        scored.sort(key=lambda x: x["final_score"], reverse=True)

        # Apply limit and assign rank
        board: list[dict[str, Any]] = []
        for i, entry in enumerate(scored[:limit], start=1):
            entry["rank"] = i
            board.append(entry)

        logger.debug("RankingService: {} items → top {}", len(items), len(board))
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
