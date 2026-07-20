"""Learning API endpoints — scoring weight configuration and optimization."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory
from app.database.scoring_repository import ScoringRepository
from app.services.learning.optimizer import ScoringOptimizer

router = APIRouter()


@router.get("/learning/config")
async def learning_config() -> dict:
    """当前评分权重配置。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ScoringRepository(session)
            config = await repo.get_active()
            if config is None:
                return {
                    "version": 0,
                    "is_active": False,
                    "weights": {
                        "sales_weight": 0.30,
                        "trend_weight": 0.25,
                        "viewer_weight": 0.15,
                        "price_weight": 0.15,
                        "competition_weight": 0.15,
                    },
                }
            return {
                "id": config.id,
                "name": config.name,
                "version": config.version,
                "is_active": config.is_active,
                "weights": config.to_weights_dict(),
                "created_at": config.created_at.isoformat() if config.created_at else None,
            }
    except Exception:
        raise HTTPException(status_code=500, detail="获取评分配置失败")


@router.post("/learning/optimize")
async def learning_optimize() -> dict:
    """手动触发一次权重优化。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            optimizer = ScoringOptimizer(session)
            return await optimizer.optimize()
    except Exception:
        raise HTTPException(status_code=500, detail="权重优化失败")


@router.get("/learning/history")
async def learning_history(limit: int = 10) -> list[dict]:
    """查看评分配置历史版本。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ScoringRepository(session)
            configs = await repo.get_history(limit=limit)
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "version": c.version,
                    "is_active": c.is_active,
                    "weights": c.to_weights_dict(),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in configs
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取配置历史失败")
