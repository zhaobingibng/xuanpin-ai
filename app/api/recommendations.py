"""Recommendation API endpoints."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory
from app.database.history_repository import HistoryRepository
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.decision.engine import ProductDecisionEngine
from app.services.lifecycle.analyzer import LifecycleAnalyzer
from app.services.recommendation.ranker import RecommendationRanker
from app.services.scoring.product_scorer import ProductScorer

router = APIRouter()


@router.get("/recommendations/today")
async def recommendations_today() -> list[dict]:
    """今日最终推荐：融合评分+趋势+生命周期+决策的最终排序。"""
    try:
        from app.services.product_service import ProductService

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            product_service = ProductService(session)
            products = await product_service.list_all(limit=10_000)

            scorer = ProductScorer()
            lifecycle_analyzer = LifecycleAnalyzer(session)
            decision_engine = ProductDecisionEngine()
            history_repo = HistoryRepository(session)
            ranker = RecommendationRanker()

            scored: list[dict] = []
            for product in products:
                history = list(await history_repo.get_history(product.id))
                score_result = scorer.calculate_score(product, history or None)
                lifecycle_result = await lifecycle_analyzer.analyze(product.id)
                decision = decision_engine.decide(
                    product, score_result["score"], lifecycle_result["stage"]
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
                    "lifecycle": lifecycle_result["stage"],
                    "decision": decision,
                    "trend_score": trend_score,
                    "reasons": score_result["reasons"],
                })

            ranked = ranker.rank(scored)

            return [
                {
                    "rank": item["rank"],
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "price": item["price"],
                    "recommend_score": item["recommend_score"],
                    "score": item["score"],
                    "lifecycle": item["lifecycle"],
                    "action": item["action"],
                    "confidence": item["confidence"],
                    "reasons": item["reasons"],
                }
                for item in ranked
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取今日推荐失败")


@router.get("/recommendations/daily")
async def recommendations_daily() -> dict:
    """今日完整推荐：统一生成流程的最终输出。"""
    try:
        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyRecommendationService(session)
            result = await svc.generate()

            return {
                "date": result["date"],
                "total": result["total"],
                "items": [
                    {
                        "rank": item["rank"],
                        "product_id": item["product_id"],
                        "name": item["name"],
                        "image": item.get("image", ""),
                        "price": item.get("price", 0.0),
                        "recommend_score": item["recommend_score"],
                        "score": item["score"],
                        "trend_score": item.get("trend_score", 50.0),
                        "lifecycle": item["lifecycle"],
                        "action": item["action"],
                        "confidence": item["confidence"],
                        "status": item.get("status", "ACTIVE"),
                        "reasons": item.get("reasons", []),
                    }
                    for item in result["items"]
                ],
            }
    except Exception:
        raise HTTPException(status_code=500, detail="获取每日推荐失败")


@router.get("/recommendations/stats")
async def recommendations_stats() -> dict:
    """推荐统计：按 action 分布计数。"""
    try:
        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyRecommendationService(session)
            result = await svc.generate()

            stats = {"sell": 0, "test": 0, "watch": 0, "drop": 0}
            for item in result["items"]:
                action = item.get("action", "").lower()
                if action in stats:
                    stats[action] += 1
            return stats
    except Exception:
        raise HTTPException(status_code=500, detail="获取推荐统计失败")


@router.get("/recommendations/opportunities")
async def recommendations_opportunities() -> list[dict]:
    """高机会商品列表：按 recommend_score×0.7 + competition_score×0.3 排序。"""
    try:
        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyRecommendationService(session)
            result = await svc.generate()

            # 计算 opportunity_score 并排序
            items = result["items"]
            for item in items:
                comp_score = item.get("competition_score") or 0
                rec_score = item.get("recommend_score", 0)
                item["opportunity_score"] = round(rec_score * 0.7 + comp_score * 0.3, 1)

            # 按 opportunity_score 降序排列
            items.sort(key=lambda x: -x["opportunity_score"])

            # 重新分配 rank
            output: list[dict] = []
            for i, item in enumerate(items, start=1):
                decision = item.get("decision", {})
                reasons = item.get("reasons", [])
                if isinstance(decision, dict):
                    reasons = reasons + decision.get("reason", [])
                output.append({
                    "rank": i,
                    "name": item["name"],
                    "price": item.get("price", 0.0),
                    "score": item["score"],
                    "recommend_score": item.get("recommend_score", 0),
                    "competition_score": item.get("competition_score", 0),
                    "market_level": item.get("market_level", "MEDIUM"),
                    "action": item.get("action", "WATCH"),
                    "reasons": reasons,
                })

            return output
    except Exception:
        raise HTTPException(status_code=500, detail="获取机会分析失败")
