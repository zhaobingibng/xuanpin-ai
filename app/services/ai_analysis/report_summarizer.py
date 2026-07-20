"""LLM-powered daily report summarizer — natural language report interpretation."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.ai.llm_client import get_llm_client
from app.ai.prompts import DAILY_REPORT_SUMMARY_SYSTEM, DAILY_REPORT_SUMMARY_USER
from app.models.daily_report import DailyReport


class LLMReportSummarizer:
    """LLM 每日报告摘要服务。

    调用 LLM 对每日选品报告生成自然语言解读。
    LLM 不可用时返回 None，调用方可降级到规则摘要。

    Usage::

        summarizer = LLMReportSummarizer()
        result = await summarizer.summarize(report)
        # {"summary": "...", "highlights": [...], ...} 或 None
    """

    async def summarize(self, report: DailyReport) -> dict[str, Any] | None:
        """为每日报告生成 LLM 摘要。

        Args:
            report: DailyReport ORM 对象（需已加载 items 关系）。

        Returns:
            包含 summary, highlights, warnings, action_items,
            market_trend 的字典，或 None。
        """
        client = get_llm_client()
        if not client.available:
            logger.debug("[LLMReportSummarizer] LLM 不可用，跳过摘要生成")
            return None

        # 构建 TOP10 商品明细文本
        top_items_text = self._build_top_items_text(report)

        user_prompt = DAILY_REPORT_SUMMARY_USER.format(
            report_date=str(report.report_date),
            total=report.total,
            hot_products=report.hot_products,
            potential_products=report.potential_products,
            average_score=report.average_score,
            top_items=top_items_text,
        )

        result = await client.chat_json(
            user_prompt=user_prompt,
            system_prompt=DAILY_REPORT_SUMMARY_SYSTEM,
            temperature=0.6,
        )

        if result is None:
            logger.warning("[LLMReportSummarizer] 报告 {} 摘要生成失败", report.id)
            return None

        # 验证必要字段
        validated = self._validate_result(result)
        if validated is None:
            logger.warning("[LLMReportSummarizer] 报告 {} 返回格式无效", report.id)
            return None

        logger.info("[LLMReportSummarizer] 报告 {} 摘要生成完成", report.id)
        return validated

    @staticmethod
    def _build_top_items_text(report: DailyReport) -> str:
        """构建 TOP10 商品明细文本，用于 prompt 上下文。"""
        items = getattr(report, "items", []) or []
        if not items:
            return "（无商品数据）"

        lines: list[str] = []
        for item in items[:10]:
            # 尝试解析 reasons JSON
            reasons = item.reasons or ""
            try:
                reasons_list = json.loads(reasons) if reasons.startswith("[") else [reasons]
            except json.JSONDecodeError:
                reasons_list = [reasons]

            line = (
                f"#{item.rank} {item.name} | "
                f"平台: {item.platform} | "
                f"价格: ¥{item.price} | "
                f"评分: {item.score} | "
                f"等级: {item.level} | "
                f"理由: {', '.join(str(r) for r in reasons_list[:3])}"
            )
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _validate_result(data: dict[str, Any]) -> dict[str, Any] | None:
        """验证 LLM 返回的结构是否包含必要字段。"""
        required_keys = {"summary"}
        if not required_keys.issubset(data.keys()):
            return None

        # 确保列表字段都是 list 类型
        for key in ("highlights", "warnings", "action_items"):
            if not isinstance(data.get(key), list):
                data[key] = []

        # market_trend 默认为空字符串
        if not isinstance(data.get("market_trend"), str):
            data["market_trend"] = ""

        return data
