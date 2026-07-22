"""OpportunityScorer — 商品机会评分模型 v2 (Phase 35).

五维评分 + 风险维度，为选品决策提供量化依据。

评分维度（总分 0-100）：
    1. match_score:      匹配可信度 (40%) — ProductMatcher final_score
    2. profit_score:     利润空间   (25%) — best profit_margin
    3. trend_score:      商品热度   (20%) — viewers + sales_24h
    4. competition_score: 供应竞争   (10%) — supplier count (inverted)
    5. risk_score:       风险评估   (5%)  — match quality, margin anomaly

返回结构::

    {
        "score": 78.5,           # 综合分数 0-100
        "match_score": 85.0,     # 匹配可信度
        "profit_score": 70.0,    # 利润空间
        "trend_score": 65.0,     # 商品热度
        "competition_score": 80.0,  # 竞争评分
        "risk_score": 90.0,      # 风险评分
        "reasons": [...],        # 推荐理由
    }

与旧版 OpportunityScoringService 保持独立，原接口不受影响。
"""

from __future__ import annotations

from typing import Any

from app.matching.embedding_service import EmbeddingService


class OpportunityScorer:
    """商品机会评分引擎 v2。

    综合 5 个维度评估商品跟卖机会，输出 0-100 综合分及分项。

    Usage::

        scorer = OpportunityScorer()
        result = scorer.calculate(product, matches)
        # result["score"] → 78.5
    """

    # ── 权重配置 ──────────────────────────────────────────

    WEIGHT_MATCH = 0.40
    WEIGHT_PROFIT = 0.25
    WEIGHT_TREND = 0.20
    WEIGHT_COMPETITION = 0.10
    WEIGHT_RISK = 0.05

    # ── 阈值 ──────────────────────────────────────────────

    PROFIT_HIGH = 70       # 利润率 ≥70% → 高分
    PROFIT_GOOD = 50
    PROFIT_OK = 30

    TREND_VIEWERS_HIGH = 5000
    TREND_SALES_HIGH = 500

    MATCH_STRONG = 0.80    # final_score ≥ 0.80 → 强匹配
    MATCH_GOOD = 0.60
    MATCH_OK = 0.40

    # ── Public API ────────────────────────────────────────

    def calculate(
        self,
        product: Any,
        matches: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """计算商品跟卖机会综合评分。

        Args:
            product: 商品对象 (Product ORM 或 dict-like)。
                需含: ``price``, ``viewers``, ``sales_24h``,
                ``name``, ``shop``.
            matches: 匹配结果列表，每项需含:
                ``final_score``, ``profit_margin``, ``title``.
                可为 ProductMatcher 返回的 dict 或 SupplierMatch 对象。

        Returns:
            Dict with: score, match_score, profit_score, trend_score,
            competition_score, risk_score, reasons.
        """
        matches = matches or []

        # ── 1. 匹配可信度 ─────────────────────────────────
        match_score, match_reason = self._score_match(matches)

        # ── 2. 利润空间 ───────────────────────────────────
        profit_score, profit_reason = self._score_profit(product, matches)

        # ── 3. 商品热度 ───────────────────────────────────
        trend_score, trend_reason = self._score_trend(product)

        # ── 4. 竞争评分 ───────────────────────────────────
        competition_score, comp_reason = self._score_competition(matches)

        # ── 5. 风险评估 ───────────────────────────────────
        risk_score, risk_reason = self._score_risk(matches)

        # ── 综合分 ────────────────────────────────────────
        composite = (
            match_score * self.WEIGHT_MATCH
            + profit_score * self.WEIGHT_PROFIT
            + trend_score * self.WEIGHT_TREND
            + competition_score * self.WEIGHT_COMPETITION
            + risk_score * self.WEIGHT_RISK
        )
        composite = round(min(composite, 100.0), 1)

        # ── 汇总理由 ──────────────────────────────────────
        reasons = self._build_reasons(
            composite, match_reason, profit_reason,
            trend_reason, comp_reason, risk_reason,
        )

        return {
            "score": composite,
            "match_score": round(match_score, 1),
            "profit_score": round(profit_score, 1),
            "trend_score": round(trend_score, 1),
            "competition_score": round(competition_score, 1),
            "risk_score": round(risk_score, 1),
            "reasons": reasons,
        }

    # ── 推荐等级 ──────────────────────────────────────────

    @staticmethod
    def get_recommendation(score: float) -> str:
        """根据综合分返回推荐等级。

        - 90-100: ★★★★★ 强烈推荐
        - 75-89:  ★★★★ 值得研究
        - 60-74:  ★★★ 观察
        - <60:    暂不推荐
        """
        if score >= 90:
            return "★★★★★ 强烈推荐"
        elif score >= 75:
            return "★★★★ 值得研究"
        elif score >= 60:
            return "★★★ 观察"
        return "暂不推荐"

    # ── 私有评分方法 ─────────────────────────────────────

    def _score_match(
        self, matches: list[dict[str, Any]],
    ) -> tuple[float, str]:
        """匹配可信度评分 (0-100)。"""
        if not matches:
            return 0.0, "无匹配供应商"

        best = self._best_final_score(matches)
        count = len(matches)
        good_count = sum(
            1 for m in matches
            if self._get_final_score(m) >= self.MATCH_OK
        )

        # 以 best final_score 为主 (0-80)
        score = min(best * 100, 80.0)

        # 好的匹配数量加分 (0-20)
        if good_count >= 5:
            score += 20.0
        elif good_count >= 3:
            score += 15.0
        elif good_count >= 1:
            score += 10.0

        score = min(score, 100.0)

        if best >= self.MATCH_STRONG:
            reason = f"匹配度高 ({best:.0%}), {good_count}个可用供应商"
        elif best >= self.MATCH_GOOD:
            reason = f"匹配度中等 ({best:.0%})"
        else:
            reason = f"匹配度偏低 ({best:.0%})"

        return score, reason

    def _score_profit(
        self, product: Any, matches: list[dict[str, Any]],
    ) -> tuple[float, str]:
        """利润空间评分 (0-100)。"""
        if not matches:
            return 0.0, "无匹配数据, 无法计算利润"

        best_margin = self._best_profit_margin(matches)
        price = self._get_product_price(product)

        if best_margin >= self.PROFIT_HIGH:
            score = 95.0
            reason = f"利润空间大 (利润率 {best_margin:.0f}%)"
        elif best_margin >= self.PROFIT_GOOD:
            score = 75.0
            reason = f"利润空间良好 (利润率 {best_margin:.0f}%)"
        elif best_margin >= self.PROFIT_OK:
            score = 50.0
            reason = f"利润空间一般 (利润率 {best_margin:.0f}%)"
        elif best_margin > 0:
            score = 25.0
            reason = f"利润空间较低 (利润率 {best_margin:.0f}%)"
        else:
            score = 5.0
            reason = "无利润空间"

        return score, reason

    def _score_trend(self, product: Any) -> tuple[float, str]:
        """商品热度评分 (0-100)，基于 viewers + sales_24h。"""
        viewers = self._get_viewers(product)
        sales_24h = self._get_sales_24h(product)

        # Viewers: 0-60 分
        if viewers >= self.TREND_VIEWERS_HIGH:
            v_score = 60.0
        elif viewers >= 2000:
            v_score = 45.0
        elif viewers >= 500:
            v_score = 30.0
        elif viewers > 0:
            v_score = 15.0
        else:
            v_score = 0.0

        # Sales: 0-40 分
        if sales_24h >= self.TREND_SALES_HIGH:
            s_score = 40.0
        elif sales_24h >= 100:
            s_score = 30.0
        elif sales_24h >= 10:
            s_score = 15.0
        elif sales_24h > 0:
            s_score = 5.0
        else:
            s_score = 0.0

        score = min(v_score + s_score, 100.0)

        parts = []
        if viewers > 0:
            parts.append(f"浏览{viewers}")
        if sales_24h > 0:
            parts.append(f"24h售{sales_24h}")
        if parts:
            reason = f"商品热度: {', '.join(parts)}"
        else:
            reason = "暂无热度数据"
            score = 10.0  # floor

        return score, reason

    def _score_competition(
        self, matches: list[dict[str, Any]],
    ) -> tuple[float, str]:
        """竞争评分 (0-100)，供应商越少分越高。"""
        count = len(matches)
        good_count = sum(
            1 for m in matches
            if self._get_final_score(m) >= self.MATCH_OK
        )

        if not matches:
            return 0.0, "无供应商"

        if count == 1:
            score = 100.0
            reason = "独家供应商, 竞争极少"
        elif count <= 3:
            score = 85.0
            reason = f"仅 {count} 个供应商, 竞争少"
        elif count <= 5:
            score = 70.0
            reason = f"{count} 个供应商, 竞争适中"
        elif count <= 10:
            score = 50.0
            reason = f"{count} 个供应商, 竞争较多"
        else:
            score = 30.0
            reason = f"{count} 个供应商, 竞争激烈"

        return score, reason

    def _score_risk(
        self, matches: list[dict[str, Any]],
    ) -> tuple[float, str]:
        """风险评估 (0-100)，风险越低分越高。"""
        if not matches:
            return 10.0, "无供应商, 无法跟卖 → 高风险"

        best_match = self._best_final_score(matches)
        best_margin = self._best_profit_margin(matches)
        good_count = sum(
            1 for m in matches
            if self._get_final_score(m) >= self.MATCH_OK
        )

        score = 100.0
        risks: list[str] = []

        # 匹配度过低风险
        if best_match < self.MATCH_OK:
            score -= 30.0
            risks.append("匹配度偏低")
        elif best_match < self.MATCH_GOOD:
            score -= 15.0
            risks.append("匹配度一般")

        # 利润过高 → 可能是假商品（价格异常）
        if best_margin > 90:
            score -= 15.0
            risks.append("利润率异常高(疑似虚假)")

        # 单点故障风险
        if good_count == 1:
            score -= 10.0
            risks.append("仅1个可匹配供应商")
        elif good_count == 0 and matches:
            score -= 25.0
            risks.append("无可匹配供应商(匹配度均不达标)")

        score = max(score, 0.0)

        if not risks:
            reason = "风险低, 匹配质量可靠"
        elif len(risks) == 1:
            reason = f"⚠️ {risks[0]}"
        else:
            reason = "⚠️ " + "; ".join(risks)

        return score, reason

    # ── 理由聚合 ──────────────────────────────────────────

    def _build_reasons(
        self,
        composite: float,
        match_reason: str,
        profit_reason: str,
        trend_reason: str,
        comp_reason: str,
        risk_reason: str,
    ) -> list[str]:
        """汇总推荐理由列表。"""
        reasons: list[str] = []

        # 综合推荐
        rec = self.get_recommendation(composite)
        reasons.append(f"综合: {rec} ({composite}分)")

        # 各维度
        reasons.append(f"匹配: {match_reason}")
        reasons.append(f"利润: {profit_reason}")
        reasons.append(f"热度: {trend_reason}")
        reasons.append(f"竞争: {comp_reason}")
        reasons.append(f"风险: {risk_reason}")

        return reasons

    # ── 数据提取工具 ──────────────────────────────────────

    @staticmethod
    def _get_final_score(match: Any) -> float:
        """从 match (dict/ORM) 提取 final_score [0, 1]."""
        if isinstance(match, dict):
            return float(match.get("final_score", 0) or 0)
        return float(getattr(match, "final_score", 0) or 0)

    @staticmethod
    def _best_final_score(matches: list[Any]) -> float:
        """获取最佳匹配度。"""
        if not matches:
            return 0.0
        return max(OpportunityScorer._get_final_score(m) for m in matches)

    @staticmethod
    def _get_profit_margin(match: Any) -> float:
        """从 match 提取 profit_margin。"""
        if isinstance(match, dict):
            return float(match.get("profit_margin", 0) or 0)
        return float(getattr(match, "profit_margin", 0) or 0)

    @staticmethod
    def _best_profit_margin(matches: list[Any]) -> float:
        """获取最佳利润率。"""
        if not matches:
            return 0.0
        return max(OpportunityScorer._get_profit_margin(m) for m in matches)

    @staticmethod
    def _get_product_price(product: Any) -> float:
        """提取商品价格。"""
        if isinstance(product, dict):
            return float(product.get("price", 0) or 0)
        return float(getattr(product, "price", 0) or 0)

    @staticmethod
    def _get_viewers(product: Any) -> int:
        """提取浏览人数。"""
        if isinstance(product, dict):
            return int(product.get("viewers", 0) or 0)
        return int(getattr(product, "viewers", 0) or 0)

    @staticmethod
    def _get_sales_24h(product: Any) -> int:
        """提取24h销量。"""
        if isinstance(product, dict):
            return int(product.get("sales_24h", 0) or 0)
        return int(getattr(product, "sales_24h", 0) or 0)
