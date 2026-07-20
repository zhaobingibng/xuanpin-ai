"""Review API endpoints — recommendation effectiveness review."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory
from app.database.review_repository import ReviewRepository
from app.services.review.analyzer import RecommendationReviewService

router = APIRouter()


@router.get("/reviews/latest")
async def reviews_latest() -> dict:
    """最近一次复盘结果。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ReviewRepository(session)
            records = await repo.get_reviews(limit=100)
            if not records:
                raise HTTPException(status_code=404, detail="暂无复盘记录")

            # 按 review_date 分组，取最新日期的所有记录
            latest_date = records[0].review_date
            latest_records = [r for r in records if r.review_date == latest_date]

            total = len(latest_records)
            success = sum(1 for r in latest_records if r.result == "SUCCESS")
            failed = sum(1 for r in latest_records if r.result == "FAILED")
            normal = sum(1 for r in latest_records if r.result == "NORMAL")
            accuracy = round(success / total * 100, 1) if total > 0 else 0.0

            return {
                "date": latest_date.isoformat(),
                "total": total,
                "success": success,
                "normal": normal,
                "failed": failed,
                "accuracy": accuracy,
                "items": [
                    {
                        "id": r.id,
                        "product_id": r.product_id,
                        "result": r.result,
                        "sales_change": r.sales_change,
                        "trend_change": r.trend_change,
                    }
                    for r in latest_records
                ],
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="获取复盘记录失败")


@router.get("/reviews/accuracy")
async def reviews_accuracy() -> dict:
    """总体推荐准确率。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ReviewRepository(session)
            return await repo.get_accuracy()
    except Exception:
        raise HTTPException(status_code=500, detail="获取准确率统计失败")
