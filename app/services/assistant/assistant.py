"""SelectionAssistant — natural-language Q&A for product selection insights."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.assistant_repository import AssistantRepository
from app.database.history_repository import HistoryRepository
from app.database.knowledge_repository import KnowledgeRepository
from app.database.report_repository import ReportRepository
from app.database.review_repository import ReviewRepository
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.competition.analyzer import CompetitionAnalyzer
from app.services.product_service import ProductService


# ── Question categories ────────────────────────────────────────

_RECOMMEND_KEYWORDS = ["推荐", "卖什么", "爆款", "热卖", "值得卖", "选品"]
_TREND_KEYWORDS = ["上涨", "趋势", "增长", "涨势", "走势", "行情"]
_RISK_KEYWORDS = ["风险", "不要卖", "竞争", "避开", "红海", "慎选"]
_STRATEGY_KEYWORDS = ["文案", "运营方案", "怎么卖", "写文案", "营销", "推广方案", "话术"]
_PRODUCT_KEYWORDS = ["商品", "产品", "查询", "查看", "详情"]


class SelectionAssistant:
    """AI选品智能问答助手。

    根据用户自然语言问题分类并调用对应服务，结合知识库标签生成回答。

    支持的问题类型：
      - 推荐类：推荐、卖什么、爆款…
      - 趋势类：上涨、趋势、增长…
      - 风险类：风险、不要卖、竞争…
      - 商品类：包含商品名称关键词
      - 未知类型：返回引导提示

    Usage::

        assistant = SelectionAssistant(session)
        result = await assistant.ask("今天有什么爆款推荐？")
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._product_service = ProductService(session)
        self._history_repo = HistoryRepository(session)
        self._knowledge_repo = KnowledgeRepository(session)
        self._review_repo = ReviewRepository(session)
        self._report_repo = ReportRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def ask(self, question: str) -> dict[str, Any]:
        """处理用户问题并返回结构化回答。

        Args:
            question: 用户自然语言问题。

        Returns:
            {"answer": str, "products": list[dict], "insights": list[str]}
        """
        question = question.strip()
        if not question:
            return self._empty_response("请输入您的问题。")

        category = self._classify(question)
        logger.info("[Assistant] 问题='{}' 分类={}", question, category)

        if category == "recommend":
            result = await self._handle_recommend(question)
        elif category == "trend":
            result = await self._handle_trend(question)
        elif category == "risk":
            result = await self._handle_risk(question)
        elif category == "strategy":
            result = await self._handle_strategy(question)
        elif category == "product":
            result = await self._handle_product(question)
        else:
            result = self._handle_unknown(question)

        # 保存问答历史
        try:
            assistant_repo = AssistantRepository(self._session)
            await assistant_repo.save(question, json.dumps(result, ensure_ascii=False))
            await self._session.commit()
        except Exception as e:
            logger.warning("[Assistant] 保存问答历史失败: {}", e)

        return result

    # ── Classification ────────────────────────────────────────

    @staticmethod
    def _classify(question: str) -> str:
        """根据关键词分类问题。"""
        # 风险优先（避免"不要卖什么"被误判为推荐）
        for kw in _RISK_KEYWORDS:
            if kw in question:
                return "risk"
        for kw in _STRATEGY_KEYWORDS:
            if kw in question:
                return "strategy"
        for kw in _RECOMMEND_KEYWORDS:
            if kw in question:
                return "recommend"
        for kw in _TREND_KEYWORDS:
            if kw in question:
                return "trend"
        for kw in _PRODUCT_KEYWORDS:
            if kw in question:
                return "product"
        # 尝试匹配已有商品名称 → product 类
        return "unknown"

    # ── Handlers ──────────────────────────────────────────────

    async def _handle_recommend(self, question: str) -> dict[str, Any]:
        """处理推荐类问题：获取最新推荐列表。"""
        report = await self._report_repo.get_latest()
        if report is None or not report.items:
            return self._empty_response("暂无推荐数据，请先运行数据采集。")

        products = []
        insights = []
        for item in report.items[:10]:
            product_info = await self._build_product_info(item.product_id, item.name, item.score)
            products.append(product_info)

        insights.append(f"共推荐 {report.total} 个商品")
        if report.hot_products > 0:
            insights.append(f"其中爆款 {report.hot_products} 个")
        if report.potential_products > 0:
            insights.append(f"潜力商品 {report.potential_products} 个")

        return {
            "answer": f"为您推荐以下 {len(products)} 个商品：",
            "products": products,
            "insights": insights,
        }

    async def _handle_trend(self, question: str) -> dict[str, Any]:
        """处理趋势类问题：分析商品趋势。"""
        products = await self._product_service.list_all(limit=20)
        if not products:
            return self._empty_response("暂无商品数据，无法分析趋势。")

        trending = []
        insights = []
        for product in products[:10]:
            history = list(await self._history_repo.get_history(product.id, limit=30))
            if len(history) >= 2:
                analyzer = TrendAnalyzer(history)
                trend = analyzer.calculate_trend_score()
                if trend["trend_score"] >= 70:
                    info = await self._build_product_info(
                        product.id, product.name, int(trend["trend_score"])
                    )
                    info["reason"].append(f"趋势等级: {trend['level']}")
                    trending.append(info)

        if trending:
            trending.sort(key=lambda x: x["score"], reverse=True)
            answer = f"发现 {len(trending)} 个上升趋势商品："
            insights.append(f"共分析 {min(len(products), 10)} 个商品的趋势数据")
        else:
            answer = "当前未发现明显上升趋势的商品。"
            insights.append("建议持续关注商品数据变化")

        return {
            "answer": answer,
            "products": trending,
            "insights": insights,
        }

    async def _handle_risk(self, question: str) -> dict[str, Any]:
        """处理风险类问题：分析竞争风险。"""
        products = await self._product_service.list_all(limit=20)
        if not products:
            return self._empty_response("暂无商品数据，无法分析风险。")

        risky = []
        insights = []
        for product in products[:10]:
            competition = await CompetitionAnalyzer(self._session).analyze(product.id)
            if competition["market_level"] == "HIGH" or competition["competition_score"] < 40:
                info = await self._build_product_info(
                    product.id, product.name, competition["competition_score"]
                )
                info["reason"].append(f"竞争等级: {competition['market_level']}")
                info["reason"].extend(competition["signals"])
                risky.append(info)

        if risky:
            answer = f"发现 {len(risky)} 个高风险商品，建议谨慎："
            insights.append("高竞争市场需要差异化策略")
        else:
            answer = "当前商品竞争风险较低。"
            insights.append("整体竞争环境较为健康")

        return {
            "answer": answer,
            "products": risky,
            "insights": insights,
        }

    async def _handle_product(self, question: str) -> dict[str, Any]:
        """处理商品查询类问题：按名称搜索商品。"""
        # 从问题中提取可能的商品名称关键词
        search_term = self._extract_product_keyword(question)
        if not search_term:
            return self._empty_response("请提供具体的商品名称，例如：「查询蓝牙耳机」。")

        products = await self._product_service.list_all(limit=100)
        matched = [p for p in products if search_term in p.name]

        if not matched:
            return self._empty_response(f"未找到包含「{search_term}」的商品。")

        product_infos = []
        for product in matched[:5]:
            info = await self._build_product_info(
                product.id, product.name, int(product.ai_score or 0)
            )
            product_infos.append(info)

        return {
            "answer": f"找到 {len(product_infos)} 个与「{search_term}」相关的商品：",
            "products": product_infos,
            "insights": [f"共匹配 {len(matched)} 个商品"],
        }

    async def _handle_strategy(self, question: str) -> dict[str, Any]:
        """处理运营方案类问题：为 TOP 商品生成运营方案。"""
        from app.services.strategy.generator import ProductStrategyGenerator

        report = await self._report_repo.get_latest()
        if report is None or not report.items:
            return self._empty_response("暂无推荐数据，无法生成运营方案。请先运行数据采集。")

        # 取排名第一的商品生成方案
        top_item = report.items[0]
        product_info = {
            "product_id": top_item.product_id,
            "name": top_item.name,
            "price": top_item.price,
            "sales_24h": 100,
            "trend_score": 75.0,
            "lifecycle": "HOT",
            "knowledge_tags": [],
        }

        # 获取知识库标签
        tags = await self._knowledge_repo.get_product_tags(top_item.product_id)
        product_info["knowledge_tags"] = tags

        generator = ProductStrategyGenerator(self._session)
        strategy = await generator.generate(product_info)

        return {
            "answer": f"已为「{strategy['title']}」生成运营方案：",
            "products": [{
                "name": strategy["title"],
                "score": top_item.score,
                "reason": strategy["selling_points"],
                "tags": [t.get("name", "") for t in tags],
                "strategy": strategy,
            }],
            "insights": [
                f"标题: {strategy['title']}",
                f"卖点: {', '.join(strategy['selling_points'])}",
                f"利润率: {strategy['profit_analysis'].get('profit_margin', 'N/A')}",
            ],
        }

    @staticmethod
    def _handle_unknown(question: str) -> dict[str, Any]:
        """处理无法分类的问题。"""
        return {
            "answer": (
                "抱歉，我暂时无法理解您的问题。您可以尝试问：\n"
                "- 推荐类：「今天有什么爆款推荐？」\n"
                "- 趋势类：「哪些商品趋势在上涨？」\n"
                "- 风险类：「哪些商品竞争压力大？」\n"
                "- 商品类：「查询蓝牙耳机」"
            ),
            "products": [],
            "insights": ["支持的问题类型：推荐、趋势、风险、商品查询"],
        }

    # ── Helpers ────────────────────────────────────────────────

    async def _build_product_info(
        self, product_id: int, name: str, score: int
    ) -> dict[str, Any]:
        """构建带知识库标签的商品信息。"""
        # 获取知识库标签
        tags = await self._knowledge_repo.get_product_tags(product_id)
        tag_names = [t["name"] for t in tags]

        # 构建推荐理由
        reasons: list[str] = []
        success_tags = [t for t in tags if t["type"] == "SUCCESS_PATTERN"]
        fail_tags = [t for t in tags if t["type"] == "FAIL_PATTERN"]

        if success_tags:
            reasons.append("历史表现优秀: " + "、".join(t["name"] for t in success_tags))
        if fail_tags:
            reasons.append("存在风险标签: " + "、".join(t["name"] for t in fail_tags))

        return {
            "name": name,
            "score": score,
            "reason": reasons,
            "tags": tag_names,
        }

    @staticmethod
    def _extract_product_keyword(question: str) -> str | None:
        """从问题中提取商品名称关键词。"""
        # 移除常见前缀词
        cleaned = question
        for prefix in ["查询", "查看", "搜索", "找", "商品", "产品", "的", "？", "?", "详情"]:
            cleaned = cleaned.replace(prefix, "")
        cleaned = cleaned.strip()
        return cleaned if cleaned else None

    @staticmethod
    def _empty_response(message: str) -> dict[str, Any]:
        return {"answer": message, "products": [], "insights": []}
