"""DailySelectionAnalyzer — LLM-powered analysis for DailySelectionReport (Phase 38).

Takes a pre-computed DailySelectionReport dict (from DailySelectionReportGenerator)
and generates AI insights: overall summary, highlights, warnings, profit analysis,
market trend, and per-product notes.

LLM unavailable → rule-based fallback.  Follows the defensive LLM pattern:
never throws, always returns a valid dict.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.ai.llm_client import get_llm_client
from app.ai.prompts import (
    DAILY_SELECTION_ANALYSIS_SYSTEM,
    DAILY_SELECTION_ANALYSIS_USER,
)


class DailySelectionAnalyzer:
    """AI 每日选品报告分析器。

    接收 DailySelectionReportGenerator.generate() 产出的 report dict，
    调用 LLM 生成结构化分析洞察。LLM 不可用时降级为规则兜底。

    不依赖数据库 — 纯数据转换。

    Usage::

        analyzer = DailySelectionAnalyzer()
        result = await analyzer.analyze(report_dict)
        # {"ai_available": True, "overall_summary": "...", ...}
    """

    def __init__(self) -> None:
        pass

    # ── Public API ──────────────────────────────────────────

    async def analyze(self, report: dict[str, Any]) -> dict[str, Any]:
        """分析每日选品报告，返回结构化 AI 洞察。

        Args:
            report: DailySelectionReportGenerator.generate() 的返回 dict。
                至少需含: report_date, top_products, statistics, summary.

        Returns:
            包含以下字段的 dict:
            - ai_available: bool — LLM 是否可用
            - overall_summary: str — 整体概览
            - highlights: list[str] — 亮点
            - warnings: list[str] — 风险提醒
            - action_suggestions: list[str] — 行动建议
            - profit_insight: str — 利润洞察
            - market_trend: str — 市场趋势
            - top_pick_notes: list[dict] — TOP3 简评
            即使 LLM 不可用（ai_available=False），其余字段也有规则兜底值。
        """
        # ── 调用 LLM ──────────────────────────────────────
        llm_result = await self._call_llm(report)

        if llm_result is not None:
            validated = self._validate_result(llm_result)
            if validated is not None:
                validated["ai_available"] = True
                logger.info(
                    "[DailySelectionAnalyzer] LLM 分析完成: {}",
                    validated.get("overall_summary", "")[:50],
                )
                return validated

        # ── LLM 不可用 → 规则降级 ───────────────────────
        logger.info("[DailySelectionAnalyzer] LLM 不可用，使用规则兜底")
        return self.analyze_fallback(report)

    def analyze_fallback(self, report: dict[str, Any]) -> dict[str, Any]:
        """规则兜底分析（不依赖 LLM）。

        Args:
            report: 同 analyze().

        Returns:
            与 analyze() 同结构，ai_available=False。
        """
        statistics = report.get("statistics", {})
        top_products: list[dict[str, Any]] = report.get("top_products", []) or []

        # ── 整体概览 ──────────────────────────────────────
        overall_summary = self._build_fallback_summary(statistics, top_products)

        # ── 亮点 ──────────────────────────────────────────
        highlights = self._build_fallback_highlights(top_products)

        # ── 风险提醒 ──────────────────────────────────────
        warnings = self._build_fallback_warnings(top_products)

        # ── 行动建议 ──────────────────────────────────────
        action_suggestions = self._build_fallback_actions(statistics, top_products)

        # ── 利润洞察 ──────────────────────────────────────
        profit_insight = self._build_fallback_profit_insight(statistics, top_products)

        # ── 市场趋势 ──────────────────────────────────────
        market_trend = self._build_fallback_market_trend(statistics, top_products)

        # ── TOP3 简评 ─────────────────────────────────────
        top_pick_notes = self._build_fallback_top_notes(top_products[:3])

        return {
            "ai_available": False,
            "overall_summary": overall_summary,
            "highlights": highlights,
            "warnings": warnings,
            "action_suggestions": action_suggestions,
            "profit_insight": profit_insight,
            "market_trend": market_trend,
            "top_pick_notes": top_pick_notes,
        }

    # ── LLM Call ──────────────────────────────────────────

    async def _call_llm(self, report: dict[str, Any]) -> dict[str, Any] | None:
        """调用 LLM 生成分析。失败返回 None。"""
        try:
            client = get_llm_client()
            if not client.available:
                return None

            # ── 构建 prompt ───────────────────────────────
            user_prompt = self._build_user_prompt(report)
            if user_prompt is None:
                return None

            result = await client.chat_json(
                user_prompt=user_prompt,
                system_prompt=DAILY_SELECTION_ANALYSIS_SYSTEM,
                temperature=0.5,
                timeout=30.0,
            )
            return result

        except Exception as e:
            logger.debug("[DailySelectionAnalyzer] LLM 调用失败: {}", e)
            return None

    @staticmethod
    def _build_user_prompt(report: dict[str, Any]) -> str | None:
        """根据 report dict 构建 user prompt 文本。

        Returns None if the report is empty / invalid.
        """
        statistics = report.get("statistics", {})
        top_products: list[dict[str, Any]] = report.get("top_products", []) or []
        report_summary = report.get("summary", "")

        # 构建 TOP 商品明细文本
        top_lines: list[str] = []
        for idx, product in enumerate(top_products[:10], 1):
            supplier = product.get("supplier_info") or {}
            top_lines.append(
                f"#{idx} {product.get('title', 'N/A')} | "
                f"机会评分: {product.get('opportunity_score', 0)}分 "
                f"({product.get('recommendation', '')}) | "
                f"售价: ¥{product.get('price', 0)} | "
                f"利润率: {supplier.get('profit_margin', 'N/A')}% | "
                f"供应商: {supplier.get('match_count', 0)}家 | "
                f"预估利润: ¥{product.get('estimated_profit', 'N/A')}"
            )
            risks = product.get("risks", [])
            if risks and risks != ["无明显风险"]:
                top_lines.append(f"   风险: {'; '.join(risks[:2])}")

        dist = statistics.get("distribution", {})

        return DAILY_SELECTION_ANALYSIS_USER.format(
            report_date=report.get("report_date", ""),
            total_products=statistics.get("total_products", 0),
            matched_products=statistics.get("matched_products", 0),
            filtered_products=statistics.get("filtered_products", 0),
            avg_score=statistics.get("avg_score", 0),
            avg_profit=statistics.get("avg_profit", 0),
            high_opp_count=statistics.get("high_opportunity_count", 0),
            strong=dist.get("strongly_recommended", 0),
            worth=dist.get("worth_studying", 0),
            observe=dist.get("observe", 0),
            report_summary=report_summary or "（暂无摘要）",
            top_items="\n".join(top_lines) if top_lines else "（无商品数据）",
        )

    # ── Validation ────────────────────────────────────────

    @staticmethod
    def _validate_result(data: dict[str, Any]) -> dict[str, Any] | None:
        """验证 LLM 返回结构是否包含必要字段。

        缺失关键字段 → None（触发规则降级）。
        无效值 → 填充安全默认值。
        """
        # 必须包含 overall_summary
        if not isinstance(data.get("overall_summary"), str) or not data["overall_summary"].strip():
            return None

        # 确保列表字段都是 list 类型
        for key in ("highlights", "warnings", "action_suggestions"):
            if not isinstance(data.get(key), list):
                data[key] = []

        # 确保文本字段都是 string
        for key in ("profit_insight", "market_trend"):
            if not isinstance(data.get(key), str):
                data[key] = ""

        # 确保 top_pick_notes 是列表
        if not isinstance(data.get("top_pick_notes"), list):
            data["top_pick_notes"] = []
        else:
            # 过滤无效项
            valid_notes: list[dict[str, Any]] = []
            for note in data["top_pick_notes"]:
                if isinstance(note, dict) and isinstance(note.get("note"), str):
                    valid_notes.append({
                        "product_id": note.get("product_id", 0),
                        "note": note["note"][:50],
                    })
            data["top_pick_notes"] = valid_notes[:3]

        return data

    # ── Fallback: 规则兜底 ────────────────────────────────

    @staticmethod
    def _build_fallback_summary(
        statistics: dict[str, Any],
        top_products: list[dict[str, Any]],
    ) -> str:
        """规则生成整体概览。"""
        total = statistics.get("total_products", 0)
        matched = statistics.get("matched_products", 0)
        filtered = statistics.get("filtered_products", 0)
        high = statistics.get("high_opportunity_count", 0)
        avg_profit = statistics.get("avg_profit", 0)

        parts = [f"共扫描 {total} 件商品"]
        if matched:
            parts.append(f"{matched} 件有供应链匹配")
        if filtered:
            parts.append(f"{filtered} 件进入候选池")
        if high:
            parts.append(f"{high} 件高机会商品")

        if top_products and avg_profit > 0:
            parts.append(f"TOP 商品平均预估利润 ¥{avg_profit}")

        return "，".join(parts) + "。"

    @staticmethod
    def _build_fallback_highlights(
        top_products: list[dict[str, Any]],
    ) -> list[str]:
        """规则生成亮点。"""
        highlights: list[str] = []

        # 高分商品
        high_score = [p for p in top_products if p.get("opportunity_score", 0) >= 75]
        if high_score:
            highlights.append(f"强烈推荐 {len(high_score)} 件高分商品")

        # 高利润商品
        high_profit = [
            p for p in top_products
            if p.get("estimated_profit") is not None
            and float(p.get("estimated_profit", 0)) >= 50
        ]
        if high_profit:
            highlights.append(f"{len(high_profit)} 件商品预估利润超 ¥50")

        # 多供应商商品
        multi_supplier = [
            p for p in top_products
            if (p.get("supplier_info") or {}).get("match_count", 0) >= 3
        ]
        if multi_supplier:
            highlights.append(f"{len(multi_supplier)} 件商品有 3+ 供应商可供选择")

        # Top1 商品
        if top_products:
            top1 = top_products[0]
            highlights.append(f"TOP1: {top1.get('title', 'N/A')}")

        return highlights[:4]

    @staticmethod
    def _build_fallback_warnings(
        top_products: list[dict[str, Any]],
    ) -> list[str]:
        """规则生成风险提醒。"""
        warnings: list[str] = []

        # 收集所有商品的风险
        all_risks: list[str] = []
        for p in top_products:
            risks = p.get("risks", [])
            if risks and risks != ["无明显风险"]:
                all_risks.extend(risks)

        # 无匹配商品
        unmatched = [
            p for p in top_products
            if (p.get("supplier_info") or {}).get("match_count", 0) == 0
            or p.get("supplier_info") is None
        ]
        if unmatched:
            warnings.append(f"{len(unmatched)} 件商品暂无供应商匹配")

        # 唯一风险信号
        unique_risks: list[str] = []
        for r in all_risks[:6]:
            if r not in unique_risks:
                unique_risks.append(r)
        warnings.extend(unique_risks[:3])

        if not warnings:
            warnings.append("暂无明显风险信号")

        return warnings[:3]

    @staticmethod
    def _build_fallback_actions(
        statistics: dict[str, Any],
        top_products: list[dict[str, Any]],
    ) -> list[str]:
        """规则生成行动建议。"""
        actions: list[str] = []

        high = statistics.get("high_opportunity_count", 0)
        if high > 0:
            actions.append(f"重点关注 {high} 件高机会商品，立即联系供应商确认货源")

        # 检查是否有可立即行动的商品
        strong = [
            p for p in top_products
            if p.get("recommendation") == "STRONGLY_RECOMMENDED"
            and (p.get("supplier_info") or {}).get("match_count", 0) >= 2
        ]
        if strong:
            actions.append(f"对 '{strong[0].get('title', '')}' 等 {len(strong)} 件强推荐商品启动跟卖")

        worth = statistics.get("distribution", {}).get("worth_studying", 0)
        if worth:
            actions.append(f"研究 {worth} 件值得关注商品，跟踪竞品动态")

        actions.append("更新知识库标签，记录成功/失败模式")

        return actions[:4]

    @staticmethod
    def _build_fallback_profit_insight(
        statistics: dict[str, Any],
        top_products: list[dict[str, Any]],
    ) -> str:
        """规则生成利润洞察。"""
        avg = statistics.get("avg_profit", 0)
        high_profit = statistics.get("high_opportunity_count", 0)

        if avg <= 0:
            return "当前暂无可评估利润数据"
        if avg >= 50:
            return f"平均预估利润 ¥{avg}，利润空间可观，建议优先跟进高利润商品"
        if avg >= 20:
            return f"平均预估利润 ¥{avg}，整体利润中等，精选高利润商品操作"
        return f"平均预估利润 ¥{avg}，利润偏低，建议优化选品标准或降低采购成本"

    @staticmethod
    def _build_fallback_market_trend(
        statistics: dict[str, Any],
        top_products: list[dict[str, Any]],
    ) -> str:
        """规则生成市场趋势判断。"""
        high = statistics.get("high_opportunity_count", 0)
        total = statistics.get("filtered_products", 0) or 1
        ratio = high / total if total > 0 else 0

        if ratio >= 0.4:
            return f"本期 {high} 件高机会商品（占比 {ratio:.0%}），市场机会丰富"
        if ratio >= 0.2:
            return f"本期 {high} 件高机会商品（占比 {ratio:.0%}），市场机会适中"
        return "高机会商品占比较低，建议拓宽选品范围或调整评分阈值"

    @staticmethod
    def _build_fallback_top_notes(
        top_3: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """规则生成 TOP3 简评。"""
        notes: list[dict[str, Any]] = []
        for p in top_3:
            pid = p.get("product_id", 0)
            title = p.get("title", "")[:15]
            score = p.get("opportunity_score", 0)
            profit = p.get("estimated_profit")
            supplier = p.get("supplier_info") or {}

            if profit is not None and float(profit) > 0:
                note = f"高分高利，预估利润 ¥{profit:.0f}"
            elif score >= 75:
                note = "机会评分优异"
            elif supplier.get("match_count", 0) >= 2:
                note = "多供应商可选"
            else:
                note = "值得关注"
            notes.append({"product_id": pid, "note": note})
        return notes
