"""Product API endpoints."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory, get_session_factory
from app.database.history_repository import HistoryRepository
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.cleaner.product_cleaner import ProductCleaner
from app.services.decision.engine import ProductDecisionEngine
from app.services.lifecycle.analyzer import LifecycleAnalyzer
from app.services.scoring.product_scorer import ProductScorer

router = APIRouter()

_cleaner = ProductCleaner()


@router.get("/products")
async def list_products() -> list[dict]:
    """返回商品列表。数据库为空时返回空列表。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            products = session.query(Product).all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "platform": p.platform,
                    "price": p.price,
                    "category": _cleaner.classify(p.name),
                }
                for p in products
            ]
    except Exception:
        return []


@router.get("/products/categories")
async def category_stats() -> dict[str, int]:
    """返回各分类的商品数量统计。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            products = session.query(Product).all()
            counts: dict[str, int] = {}
            for p in products:
                cat = _cleaner.classify(p.name)
                counts[cat] = counts.get(cat, 0) + 1
            return counts
    except Exception:
        return {}


@router.get("/products/recommendations")
async def recommendations() -> list[dict]:
    """今日推荐商品：综合评分 + 生命周期 + 决策引擎。"""
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

            results: list[dict] = []
            for product in products:
                history = list(await history_repo.get_history(product.id))
                score_result = scorer.calculate_score(product, history or None)
                lifecycle_result = await lifecycle_analyzer.analyze(product.id)
                decision = decision_engine.decide(
                    product, score_result["score"], lifecycle_result["stage"]
                )
                results.append({
                    "name": product.name,
                    "score": score_result["score"],
                    "lifecycle": lifecycle_result["stage"],
                    "action": decision["action"],
                    "confidence": decision["confidence"],
                    "reasons": decision["reason"],
                })

            results.sort(key=lambda x: x["confidence"], reverse=True)
            return results
    except Exception:
        raise HTTPException(status_code=500, detail="获取推荐商品失败")


@router.get("/products/{product_id}/trend")
async def product_trend(product_id: int) -> dict:
    """返回指定商品的趋势分析结果。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            product = session.query(Product).filter_by(id=product_id).first()
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")

            history = (
                session.query(ProductHistory)
                .filter_by(product_id=product_id)
                .order_by(ProductHistory.record_time)
                .all()
            )

            analyzer = TrendAnalyzer(history)
            result = analyzer.calculate_trend_score()
            return {
                "trend_score": result["trend_score"],
                "sales_growth": result["sales_growth"],
                "view_growth": result["view_growth"],
                "price_change": result["price_change"],
                "level": result["level"],
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/products/{product_id}/detail")
async def product_detail(product_id: int) -> dict:
    """返回商品详情 + 趋势数据 + 统计数据。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            product = session.query(Product).filter_by(id=product_id).first()
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")

            # ── 趋势数据 ──────────────────────────────────────
            history = (
                session.query(ProductHistory)
                .filter_by(product_id=product_id)
                .order_by(ProductHistory.record_time)
                .all()
            )
            analyzer = TrendAnalyzer(history)
            trend_result = analyzer.calculate_trend_score()

            # ── 统计数据 ──────────────────────────────────────
            all_products = session.query(Product).all()
            category = _cleaner.classify(product.name)
            same_category = [p for p in all_products if _cleaner.classify(p.name) == category]

            # AI 分数排名（降序）
            scored = sorted(
                [p for p in all_products if p.ai_score is not None],
                key=lambda p: p.ai_score,
                reverse=True,
            )
            ai_rank = next((i + 1 for i, p in enumerate(scored) if p.id == product.id), None)

            avg_ai = (
                round(sum(p.ai_score for p in scored) / len(scored), 2)
                if scored else 0.0
            )

            return {
                # 商品详情
                "id": product.id,
                "name": product.name,
                "platform": product.platform,
                "shop": product.shop,
                "price": product.price,
                "viewers": product.viewers,
                "sales_24h": product.sales_24h,
                "ai_score": product.ai_score,
                "category": category,
                # 趋势数据
                "trend": {
                    "sales_growth": trend_result["sales_growth"],
                    "view_growth": trend_result["view_growth"],
                    "level": trend_result["level"],
                },
                # 统计数据
                "stats": {
                    "total_products": len(all_products),
                    "category_count": len(same_category),
                    "ai_rank": ai_rank,
                    "avg_ai_score": avg_ai,
                },
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/products/{product_id}")
async def get_product(product_id: int) -> dict:
    """根据 ID 返回商品详情 + 历史数据，不存在返回 404。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            product = session.query(Product).filter_by(id=product_id).first()
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")

            history = (
                session.query(ProductHistory)
                .filter_by(product_id=product_id)
                .order_by(ProductHistory.record_time)
                .all()
            )

            return {
                "id": product.id,
                "name": product.name,
                "platform": product.platform,
                "price": product.price,
                "category": _cleaner.classify(product.name),
                "history": [
                    {
                        "price": h.price,
                        "sales_24h": h.sales_24h,
                        "viewers": h.viewers,
                        "ai_score": h.ai_score,
                        "record_time": str(h.record_time),
                    }
                    for h in history
                ],
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Product not found")
