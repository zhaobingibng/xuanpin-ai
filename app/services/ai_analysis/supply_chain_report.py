"""SupplyChainReportGenerator — AI-powered supply chain analysis report."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.ai.llm_client import get_llm_client
from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch


_SYSTEM_PROMPT = """你是电商选品分析师。根据商品信息和供应链匹配数据，生成简洁的选品建议报告。

报告格式：
1. 一句话总结（20字以内）
2. 优势分析（2-3条）
3. 风险提示（1-2条）
4. 建议操作：SELL/TEST/WATCH/DROP

只返回 JSON 格式：
{"summary": "...", "advantages": ["...", "..."], "risks": ["..."], "action": "SELL/TEST/WATCH/DROP"}"""


class SupplyChainReportGenerator:
    """生成包含供应链信息的 AI 选品报告。

    整合商品数据、供应链匹配结果、利润分析，调用 LLM 生成综合建议。
    LLM 不可用时降级为纯数据报告。

    Usage::

        gen = SupplyChainReportGenerator()
        report = await gen.generate(product, match)
    """

    async def generate(
        self,
        product: Product,
        match: SupplyChainMatch | None = None,
    ) -> dict[str, Any]:
        """生成供应链选品报告。

        Args:
            product: 目标商品。
            match: 供应链匹配结果（可选）。

        Returns:
            报告字典:
            {
                "product_id": int,
                "product_name": str,
                "summary": str,
                "advantages": list[str],
                "risks": list[str],
                "action": str,
                "supply_chain": dict | None,
                "llm_available": bool,
            }
        """
        # 构建基础数据
        report: dict[str, Any] = {
            "product_id": product.id,
            "product_name": product.name,
            "price": product.price,
            "platform": product.platform,
            "shop": product.shop,
            "summary": "",
            "advantages": [],
            "risks": [],
            "action": "WATCH",
            "supply_chain": None,
            "llm_available": False,
        }

        # 添加供应链信息
        if match is not None:
            report["supply_chain"] = {
                "match_score": match.match_score,
                "cost_price": match.cost_price,
                "sell_price": match.sell_price,
                "profit_margin": match.profit_margin,
                "profit_amount": match.profit_amount,
                "source_id": match.source_product_external_id,
            }

            # 根据利润率决定默认 action
            if match.profit_margin >= 40:
                report["action"] = "SELL"
            elif match.profit_margin >= 20:
                report["action"] = "TEST"
            elif match.profit_margin >= 0:
                report["action"] = "WATCH"
            else:
                report["action"] = "DROP"

        # 尝试 LLM 增强
        try:
            client = get_llm_client()
            if client.available:
                llm_result = await self._generate_with_llm(product, match)
                if llm_result:
                    report.update(llm_result)
                    report["llm_available"] = True
        except Exception as e:
            logger.debug("[SupplyChainReport] LLM 不可用，使用默认报告: {}", e)

        # 如果 LLM 未生成 summary，使用默认
        if not report["summary"]:
            report["summary"] = self._generate_default_summary(product, match)

        return report

    async def _generate_with_llm(
        self,
        product: Product,
        match: SupplyChainMatch | None,
    ) -> dict[str, Any] | None:
        """调用 LLM 生成分析报告。"""
        try:
            client = get_llm_client()
            if not client.available:
                return None

            # 构建 prompt
            user_prompt = f"""商品名称: {product.name}
售价: {product.price} 元
平台: {product.platform}
店铺: {product.shop}
"""
            if match:
                user_prompt += f"""
供应链匹配:
- 1688采购价: {match.cost_price} 元
- 匹配度: {match.match_score:.0%}
- 利润率: {match.profit_margin:.1f}%
- 利润额: {match.profit_amount:.2f} 元
"""

            result = await client.chat(
                user_prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.5,
                timeout=10.0,
            )

            if result:
                import json
                try:
                    parsed = json.loads(result.strip())
                    return {
                        "summary": parsed.get("summary", ""),
                        "advantages": parsed.get("advantages", []),
                        "risks": parsed.get("risks", []),
                        "action": parsed.get("action", "WATCH"),
                    }
                except json.JSONDecodeError:
                    # LLM 返回非 JSON，作为 summary 处理
                    return {"summary": result.strip()[:100]}

        except Exception as e:
            logger.debug("[SupplyChainReport] LLM 分析失败: {}", e)

        return None

    @staticmethod
    def _generate_default_summary(
        product: Product,
        match: SupplyChainMatch | None,
    ) -> str:
        """生成默认摘要（LLM 不可用时）。"""
        if match is None:
            return f"商品 '{product.name[:20]}' 未找到供应链匹配数据"

        if match.profit_margin >= 30:
            return f"高利润商品: 利润率 {match.profit_margin:.1f}%，建议重点跟进"
        elif match.profit_margin >= 15:
            return f"中等利润: 利润率 {match.profit_margin:.1f}%，可小规模测试"
        elif match.profit_margin >= 0:
            return f"低利润: 利润率 {match.profit_margin:.1f}%，需谨慎评估"
        else:
            return f"利润为负: 利润率 {match.profit_margin:.1f}%，不建议入场"
