"""Ranking API endpoints."""

from fastapi import APIRouter

from app.database.base import get_session_factory
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.ranking.ranking import RankingService

router = APIRouter()


@router.get("/ranking/top100")
async def top100() -> list[dict]:
    """返回 TOP 100 商品排行榜。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            products = session.query(Product).all()

            if not products:
                return []

            # Build history lookup: product_id → list[ProductHistory]
            history_map: dict[int, list[ProductHistory]] = {}
            histories = session.query(ProductHistory).all()
            for h in histories:
                history_map.setdefault(h.product_id, []).append(h)

            # Build items for RankingService
            items = []
            for p in products:
                trend_score = 0.0
                if p.id in history_map:
                    analyzer = TrendAnalyzer(history_map[p.id])
                    result = analyzer.calculate_trend_score()
                    trend_score = result["trend_score"]

                items.append({
                    "product": p,
                    "ai_score": p.ai_score or 0.0,
                    "trend_score": trend_score,
                })

            service = RankingService()
            board = service.get_top_products(items, limit=100)

            return [
                {
                    "rank": entry["rank"],
                    "product_id": entry["product_id"],
                    "name": entry["name"],
                    "platform": entry["platform"],
                    "price": entry["price"],
                    "ai_score": entry["ai_score"],
                    "trend_score": entry["trend_score"],
                    "final_score": entry["final_score"],
                    "level": entry["level"],
                }
                for entry in board
            ]
    except Exception:
        return []
