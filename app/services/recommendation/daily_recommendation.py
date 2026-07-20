"""Daily recommendation service — full pipeline from products to ranked recommendations."""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.history_repository import HistoryRepository
from app.database.knowledge_repository import KnowledgeRepository
from app.database.recommendation_repository import RecommendationRepository
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.competition.analyzer import CompetitionAnalyzer
from app.services.decision.engine import ProductDecisionEngine
from app.services.lifecycle.analyzer import LifecycleAnalyzer
from app.services.product_service import ProductService
from app.services.recommendation.ranker import RecommendationRanker
from app.services.scoring.product_scorer import ProductScorer


class DailyRecommendationService:
    """每日推荐服务 — 完整的采集→评分→排序→保存流程。

    流程:
        ProductService → HistoryRepository → ProductScorer →
        TrendAnalyzer → LifecycleAnalyzer → ProductDecisionEngine →
        RecommendationRanker → RecommendationRepository

    Usage::

        svc = DailyRecommendationService(session)
        result = await svc.generate()
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._product_service = ProductService(session)
        self._history_repo = HistoryRepository(session)
        self._recommendation_repo = RecommendationRepository(session)
        self._knowledge_repo = KnowledgeRepository(session)
        self._scorer = ProductScorer()
        self._lifecycle = LifecycleAnalyzer(session)
        self._competition = CompetitionAnalyzer(session)
        self._decision = ProductDecisionEngine()
        self._ranker = RecommendationRanker()

    # ── Public API ────────────────────────────────────────────

    async def generate(self) -> dict[str, Any]:
        """生成每日推荐。

        每天唯一保护：同一天重复调用时覆盖旧推荐。

        Returns:
            {"date": str, "total": int, "items": list[dict]}
        """
        # 1. 获取候选商品
        products = await self._product_service.list_all(limit=10_000)

        if not products:
            logger.info("[DailyRecommendation] 无商品数据")
            return {
                "date": date.today().isoformat(),
                "total": 0,
                "items": [],
            }

        # 2-6. 逐个评分 + 趋势 + 生命周期 + 竞争分析 + 决策
        scored: list[dict[str, Any]] = []
        for product in products:
            history = list(await self._history_repo.get_history(product.id))
            score_result = self._scorer.calculate_score(product, history or None)
            lifecycle_result = await self._lifecycle.analyze(product.id)
            competition_result = await self._competition.analyze(product.id)
            decision_result = self._decision.decide(
                product,
                score_result["score"],
                lifecycle_result["stage"],
                competition_score=competition_result["competition_score"],
                market_level=competition_result["market_level"],
            )
            trend_score = 50.0
            if history and len(history) >= 2:
                analyzer = TrendAnalyzer(history)
                trend_score = analyzer.calculate_trend_score()["trend_score"]
            scored.append({
                "product_id": product.id,
                "name": product.name,
                "platform": product.platform,
                "image": product.image or "",
                "price": product.price,
                "score": score_result["score"],
                "level": score_result["level"],
                "reasons": score_result["reasons"],
                "lifecycle": lifecycle_result["stage"],
                "competition_score": competition_result["competition_score"],
                "market_level": competition_result["market_level"],
                "decision": decision_result,
                "trend_score": trend_score,
                "knowledge_tags": await self._knowledge_repo.get_product_tags(product.id),
            })

        # 7. 排序
        ranked = self._ranker.rank(scored)

        # 8. 添加 status 字段
        for item in ranked:
            item["status"] = "ACTIVE"

        # 9. 保存推荐结果（每日唯一保护）
        try:
            await self._recommendation_repo.save_daily_recommendations(ranked)
        except Exception as e:
            logger.warning("[DailyRecommendation] 保存失败: {}", e)

        report = {
            "date": date.today().isoformat(),
            "total": len(ranked),
            "items": ranked,
        }

        logger.info(
            "[DailyRecommendation] date={}, total={}",
            report["date"], report["total"],
        )
        return report
