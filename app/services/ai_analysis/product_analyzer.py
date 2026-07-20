"""LLM-powered product analyzer — deep analysis using language models."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.ai.llm_client import get_llm_client
from app.ai.prompts import PRODUCT_ANALYSIS_SYSTEM, PRODUCT_ANALYSIS_USER
from app.models.product import Product


class LLMProductAnalyzer:
    """LLM 商品智能分析服务。

    调用 LLM 对单个商品进行深度分析，返回结构化结果。
    LLM 不可用时返回 None，调用方可降级到规则引擎。

    Usage::

        analyzer = LLMProductAnalyzer()
        result = await analyzer.analyze(product)
        # {"summary": "...", "tags": [...], ...} 或 None
    """

    async def analyze(self, product: Product) -> dict[str, Any] | None:
        """分析单个商品，返回结构化分析结果。

        Args:
            product: Product ORM 对象。

        Returns:
            包含 summary, tags, market_insight, selling_points,
            risks, recommendation, confidence 的字典，或 None。
        """
        client = get_llm_client()
        if not client.available:
            logger.debug("[LLMProductAnalyzer] LLM 不可用，跳过分析")
            return None

        user_prompt = PRODUCT_ANALYSIS_USER.format(
            name=product.name,
            platform=product.platform,
            shop=product.shop,
            price=product.price,
            sales_24h=product.sales_24h,
            viewers=product.viewers,
            category=product.category or "未分类",
            lifecycle_stage=product.lifecycle_stage,
            ai_score=product.ai_score or 0,
        )

        result = await client.chat_json(
            user_prompt=user_prompt,
            system_prompt=PRODUCT_ANALYSIS_SYSTEM,
            temperature=0.5,
        )

        if result is None:
            logger.warning("[LLMProductAnalyzer] 商品 '{}' 分析失败", product.name)
            return None

        # 验证必要字段
        validated = self._validate_result(result)
        if validated is None:
            logger.warning("[LLMProductAnalyzer] 商品 '{}' 返回格式无效", product.name)
            return None

        logger.info("[LLMProductAnalyzer] 商品 '{}' 分析完成: {}", product.name, validated.get("summary", ""))
        return validated

    async def analyze_batch(self, products: list[Product]) -> list[dict[str, Any] | None]:
        """批量分析商品。

        单个失败不影响其他，失败的返回 None 占位。

        Args:
            products: Product ORM 对象列表。

        Returns:
            与输入顺序对应的分析结果列表。
        """
        results: list[dict[str, Any] | None] = []
        for product in products:
            result = await self.analyze(product)
            results.append(result)
        return results

    @staticmethod
    def _validate_result(data: dict[str, Any]) -> dict[str, Any] | None:
        """验证 LLM 返回的结构是否包含必要字段。"""
        required_keys = {"summary", "tags", "recommendation"}
        if not required_keys.issubset(data.keys()):
            return None

        # 确保 recommendation 是有效值
        valid_actions = {"SELL", "TEST", "WATCH", "DROP"}
        rec = str(data.get("recommendation", "")).upper()
        if rec not in valid_actions:
            data["recommendation"] = "WATCH"
        else:
            data["recommendation"] = rec

        # 确保 tags 是列表
        if not isinstance(data.get("tags"), list):
            data["tags"] = []

        # 确保 selling_points 是列表
        if not isinstance(data.get("selling_points"), list):
            data["selling_points"] = []

        # 确保 risks 是列表
        if not isinstance(data.get("risks"), list):
            data["risks"] = []

        # 确保 confidence 是整数
        try:
            data["confidence"] = int(data.get("confidence", 50))
        except (TypeError, ValueError):
            data["confidence"] = 50

        return data
