"""Product decision engine — combine score + lifecycle into actionable recommendations."""

from __future__ import annotations

from typing import Any

from app.models.product import Product


class ProductDecisionEngine:
    """自动选品决策引擎。

    综合评分 + 生命周期 + 竞争分析 → 推荐动作：
      - SELL:  score >= 90 且 lifecycle == HOT 且 competition_score >= 70
      - TEST:  score >= 70 且 lifecycle == RISING
      - WATCH: score 50-69（或 score >= 70 但生命周期不匹配）
      - DROP:  score < 50  或 lifecycle == DECLINE
               或 lifecycle == DECLINE 且 market_level == HIGH

    当 competition_score 为 None 时按原始逻辑（不考虑竞争度）。

    Usage::

        engine = ProductDecisionEngine()
        result = engine.decide(product, score=95, lifecycle="HOT", competition_score=80)
    """

    def decide(
        self,
        product: Product,
        score: int,
        lifecycle: str,
        competition_score: int | None = None,
        market_level: str | None = None,
    ) -> dict[str, Any]:
        """根据评分、生命周期和竞争分析生成决策建议。

        Args:
            product: 商品 ORM 实例。
            score: 综合评分（0-100）。
            lifecycle: 生命周期阶段（NEW/RISING/HOT/DECLINE）。
            competition_score: 竞争评分（0-100），None 时不参与判断。
            market_level: 市场等级（LOW/MEDIUM/HIGH），None 时不参与判断。

        Returns:
            {"action": str, "confidence": int, "reason": list[str]}
        """
        # ── DECLINE 优先判断（即使评分较高也建议放弃） ─────────
        if lifecycle == "DECLINE":
            confidence = max(10, 50 - score)
            reason = ["商品衰退", f"评分{score}"]
            # DECLINE + HIGH 市场 → 强烈建议放弃
            if market_level == "HIGH":
                reason.append("市场竞争激烈")
                confidence = min(100, confidence + 20)
            return {"action": "DROP", "confidence": confidence, "reason": reason}

        # ── 低评分直接放弃 ─────────────────────────────────────
        if score < 50:
            confidence = max(10, 50 - score)
            reason = [f"评分{score}偏低"]
            return {"action": "DROP", "confidence": confidence, "reason": reason}

        # ── 强烈推荐：高评分 + 爆款阶段 + 竞争度优势 ───────────
        if score >= 90 and lifecycle == "HOT":
            # 有竞争度数据时需满足 competition_score >= 70
            if competition_score is not None and competition_score < 70:
                # 竞争度不够 → 降级为 TEST
                confidence = min(90, 70 + (score - 70))
                reason = ["高评分", "爆款阶段", f"竞争度{competition_score}偏低"]
                return {"action": "TEST", "confidence": confidence, "reason": reason}
            confidence = min(100, 90 + (score - 90))
            reason = ["高评分", "爆款阶段"]
            if competition_score is not None:
                reason.append(f"竞争度{competition_score}")
            return {"action": "SELL", "confidence": confidence, "reason": reason}

        # ── 推荐测试：中高评分 + 增长阶段 ───────────────────────
        if score >= 70 and lifecycle == "RISING":
            confidence = min(90, 70 + (score - 70))
            reason = ["增长阶段", "建议小批量测试"]
            return {"action": "TEST", "confidence": confidence, "reason": reason}

        # ── 中等评分：观察 ─────────────────────────────────────
        if 50 <= score <= 69:
            confidence = max(30, 60 - abs(score - 60))
            reason = [f"评分{score}", "建议继续观察"]
            return {"action": "WATCH", "confidence": confidence, "reason": reason}

        # ── score >= 70 但 lifecycle 不匹配 → 观察 ────────────
        confidence = 50
        reason = [f"评分{score}", f"生命周期{lifecycle}", "暂无明确建议"]
        return {"action": "WATCH", "confidence": confidence, "reason": reason}
