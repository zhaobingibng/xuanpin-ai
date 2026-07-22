"""DailySelectionReportGenerator — 每日选品决策报告生成器 v2 (Phase 36).

Stateless report builder that takes pre-computed products/matches/scores
and produces a structured JSON daily selection report.

与旧版 DailySelectionReportService 和 DailyReportService 独立共存，
互不影响。不依赖数据库 — 纯数据转换。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.services.opportunity.scorer import OpportunityScorer


# ── 最低评分阈值 ───────────────────────────────────────────

MIN_SCORE_THRESHOLD = 30  # 低于此分自动过滤


class DailySelectionReportGenerator:
    """每日选品决策报告生成器 v2。

    接收预计算好的商品列表、匹配结果、机会评分，
    输出结构化 JSON 日报。

    Usage::

        generator = DailySelectionReportGenerator()
        report = generator.generate(products, matches, limit=20)
        # report = {
        #     "report_date": "2026-07-22",
        #     "summary": "...",
        #     "top_products": [...],
        #     "statistics": {...},
        # }
    """

    def __init__(
        self,
        scorer: OpportunityScorer | None = None,
        min_score: float = MIN_SCORE_THRESHOLD,
    ) -> None:
        """Initialize generator.

        Args:
            scorer: Optional OpportunityScorer instance (creates default if None).
            min_score: Minimum opportunity_score threshold for inclusion.
        """
        self._scorer = scorer or OpportunityScorer()
        self._min_score = min_score

    # ── Public API ──────────────────────────────────────────

    def generate(
        self,
        products: list[dict[str, Any]],
        matches: list[dict[str, Any]] | None = None,
        scores: list[dict[str, Any]] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """生成每日选品决策报告。

        Args:
            products: 商品列表，每项需含:
                ``product_id``, ``title`` (或 ``name``),
                ``price``, ``viewers``, ``sales_24h``.
            matches: 匹配结果列表，每项需含:
                ``product_id``, ``final_score``, ``profit_margin``,
                ``supplier_title``, ``supplier_price``.
                可选 — 无匹配数据时传 [] 或 None.
            scores: 预计算评分列表，每项含:
                ``product_id``, ``score``.  可选 — 不传则自动计算.
            limit: 报告中商品数量上限，默认 TOP 20.

        Returns:
            结构化日报 dict，包含:
            - report_date
            - summary (文本摘要)
            - top_products (排序后列表)
            - statistics (统计指标)
        """
        matches = matches or []
        scores = scores or []

        # ── 构建索引 ──────────────────────────────────────
        product_map = self._build_product_map(products)
        match_map = self._build_match_map(matches)
        score_map = self._build_score_map(scores)

        # ── 逐商品评分 ────────────────────────────────────
        scored_products: list[dict[str, Any]] = []
        for pid, product in product_map.items():
            product_matches = match_map.get(pid, [])

            # 使用已有评分或自动计算
            if pid in score_map:
                opp_score = score_map[pid]
            else:
                score_result = self._scorer.calculate(product, product_matches)
                opp_score = score_result["score"]

            # 自动过滤低分商品
            if opp_score < self._min_score:
                continue

            recommendation = OpportunityScorer.get_recommendation(opp_score)

            # 构建供应商信息
            supplier_info = self._build_supplier_info(product_matches)

            # 提取理由和风险
            reasons = self._extract_reasons(product, product_matches, opp_score)
            risks = self._extract_risks(product_matches)

            scored_products.append({
                "product_id": pid,
                "title": product.get("title") or product.get("name", ""),
                "price": product.get("price", 0),
                "opportunity_score": round(opp_score, 1),
                "recommendation": recommendation,
                "supplier_info": supplier_info,
                "estimated_profit": self._estimate_profit(product, product_matches),
                "reasons": reasons,
                "risks": risks,
            })

        # ── 按 opportunity_score 降序排序 ─────────────────
        sorted_products = sorted(
            scored_products,
            key=lambda x: x["opportunity_score"],
            reverse=True,
        )

        # ── Top-N 截断 ────────────────────────────────────
        top_products = sorted_products[:limit]

        # ── 统计 ──────────────────────────────────────────
        statistics = self._build_statistics(
            products, matches, top_products, sorted_products,
        )

        # ── 摘要 ──────────────────────────────────────────
        summary = self._build_summary(statistics, top_products)

        return {
            "report_date": date.today().isoformat(),
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "top_products": top_products,
            "statistics": statistics,
        }

    # ── Index Builders ─────────────────────────────────────

    @staticmethod
    def _build_product_map(
        products: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        """Build product_id → product dict lookup."""
        result: dict[int, dict[str, Any]] = {}
        for p in products or []:
            pid = p.get("product_id") or p.get("id")
            if pid is not None:
                result[int(pid)] = p
        return result

    @staticmethod
    def _build_match_map(
        matches: list[dict[str, Any]],
    ) -> dict[int, list[dict[str, Any]]]:
        """Build product_id → list of matches lookup."""
        result: dict[int, list[dict[str, Any]]] = {}
        for m in matches or []:
            pid = m.get("product_id")
            if pid is not None:
                pid = int(pid)
                result.setdefault(pid, []).append(m)
        return result

    @staticmethod
    def _build_score_map(
        scores: list[dict[str, Any]],
    ) -> dict[int, float]:
        """Build product_id → opportunity_score lookup."""
        result: dict[int, float] = {}
        for s in scores or []:
            pid = s.get("product_id")
            if pid is not None:
                result[int(pid)] = float(s.get("score", 0))
        return result

    # ── Supplier Info ──────────────────────────────────────

    @staticmethod
    def _build_supplier_info(
        matches: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Extract best supplier info from matches."""
        if not matches:
            return None

        # Find the best match (highest final_score, then profit_margin)
        best = max(
            matches,
            key=lambda m: (
                float(m.get("final_score", 0) or 0),
                float(m.get("profit_margin", 0) or 0),
            ),
        )

        supplier_price = float(best.get("supplier_price", 0) or 0)
        profit_margin = float(best.get("profit_margin", 0) or 0)

        return {
            "supplier_title": best.get("supplier_title") or best.get("title", ""),
            "supplier_price": round(supplier_price, 2),
            "supplier_product_id": best.get("supplier_product_id"),
            "profit_margin": round(profit_margin, 1),
            "final_score": round(float(best.get("final_score", 0) or 0), 3),
            "match_count": len(matches),
        }

    # ── Profit ─────────────────────────────────────────────

    @staticmethod
    def _estimate_profit(
        product: dict[str, Any],
        matches: list[dict[str, Any]],
    ) -> float | None:
        """Estimate profit from product price and best supplier price."""
        if not matches:
            return None

        price = float(product.get("price", 0) or 0)

        # Extract supplier prices, handling explicit None vs 0
        supplier_prices: list[float] = []
        for m in matches:
            sp = m.get("supplier_price")
            if sp is not None:
                supplier_prices.append(float(sp))
        if not supplier_prices:
            return None
        best_price = min(supplier_prices)

        if price == 0:
            return None

        return round(price - best_price, 2)

    # ── Reasons / Risks ────────────────────────────────────

    @staticmethod
    def _extract_reasons(
        product: dict[str, Any],
        matches: list[dict[str, Any]],
        opp_score: float,
    ) -> list[str]:
        """Generate human-readable reasons for recommendation."""
        reasons: list[str] = []

        rec = OpportunityScorer.get_recommendation(opp_score)
        reasons.append(f"机会评分: {opp_score}分 ({rec})")

        if matches:
            best = max(
                matches,
                key=lambda m: float(m.get("final_score", 0) or 0),
            )
            final = float(best.get("final_score", 0) or 0)
            margin = float(best.get("profit_margin", 0) or 0)
            reasons.append(f"匹配度: {final:.0%}")
            reasons.append(f"利润率: {margin:.0f}%")
            reasons.append(f"供应商数: {len(matches)}")
        else:
            reasons.append("暂无匹配供应商")

        viewers = product.get("viewers", 0) or 0
        sales = product.get("sales_24h", 0) or 0
        if viewers > 0 or sales > 0:
            reasons.append(f"热度: 浏览{viewers}, 24h售{sales}")

        return reasons

    @staticmethod
    def _extract_risks(
        matches: list[dict[str, Any]],
    ) -> list[str]:
        """Identify potential risks."""
        risks: list[str] = []

        if not matches:
            risks.append("无供应商匹配 — 无法跟卖")
            return risks

        best_margin = max(
            float(m.get("profit_margin", 0) or 0) for m in matches
        )
        best_match = max(
            float(m.get("final_score", 0) or 0) for m in matches
        )
        good_count = sum(
            1 for m in matches
            if float(m.get("final_score", 0) or 0) >= 0.40
        )

        if best_margin > 90:
            risks.append("利润率异常高, 可能是虚假商品")
        if best_match < 0.40:
            risks.append("匹配度偏低, 货源可信度不足")
        if good_count == 1:
            risks.append("仅1个可靠供应商, 供应风险")
        if good_count == 0 and matches:
            risks.append("无可靠供应商(匹配度均<40%)")

        if not risks:
            risks.append("无明显风险")

        return risks

    # ── Statistics ─────────────────────────────────────────

    @staticmethod
    def _build_statistics(
        products: list[dict[str, Any]],
        matches: list[dict[str, Any]],
        top_products: list[dict[str, Any]],
        all_scored: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build statistics for the report."""
        total_products = len(products)

        # Matched products count
        match_pids = set()
        for m in matches or []:
            pid = m.get("product_id")
            if pid is not None:
                match_pids.add(int(pid))
        matched_products = len(match_pids)

        # Average scores
        if top_products:
            avg_score = round(
                sum(p["opportunity_score"] for p in top_products)
                / len(top_products), 1
            )
        else:
            avg_score = 0.0

        # Average profit
        profits = [
            p["estimated_profit"] for p in top_products
            if p.get("estimated_profit") is not None
        ]
        avg_profit = round(sum(profits) / len(profits), 2) if profits else 0.0

        # High opportunity count
        high_opp = sum(
            1 for p in all_scored if p["opportunity_score"] >= 60
        )

        # Score distribution
        strong = sum(1 for p in all_scored if p["opportunity_score"] >= 75)
        worth = sum(
            1 for p in all_scored
            if 60 <= p["opportunity_score"] < 75
        )
        observe = sum(
            1 for p in all_scored
            if 30 <= p["opportunity_score"] < 60
        )

        return {
            "total_products": total_products,
            "matched_products": matched_products,
            "filtered_products": len(all_scored),
            "avg_score": avg_score,
            "avg_profit": avg_profit,
            "high_opportunity_count": high_opp,
            "distribution": {
                "strongly_recommended": strong,
                "worth_studying": worth,
                "observe": observe,
            },
        }

    # ── Summary ────────────────────────────────────────────

    @staticmethod
    def _build_summary(
        statistics: dict[str, Any],
        top_products: list[dict[str, Any]],
    ) -> str:
        """Generate human-readable summary text."""
        total = statistics["total_products"]
        matched = statistics["matched_products"]
        filtered = statistics["filtered_products"]
        avg_score = statistics["avg_score"]
        avg_profit = statistics["avg_profit"]
        high = statistics["high_opportunity_count"]

        parts = [
            f"共扫描 {total} 件商品，其中 {matched} 件有供应商匹配。",
            f"经评分过滤后，{filtered} 件商品进入候选池。",
        ]

        if top_products:
            parts.append(
                f"Top {len(top_products)} 平均机会评分 {avg_score}，"
                f"平均预估利润 ¥{avg_profit}。"
            )
        else:
            parts.append("暂未发现高机会商品。")

        if high > 0:
            parts.append(f"其中 {high} 件商品机会评分 ≥ 60 分。")

        parts.append(
            f"评分分布: ★★★★★{statistics['distribution']['strongly_recommended']} "
            f"| ★★★★{statistics['distribution']['worth_studying']} "
            f"| ★★★{statistics['distribution']['observe']}"
        )

        return " ".join(parts)
