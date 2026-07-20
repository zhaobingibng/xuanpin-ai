"""Strategy API endpoints — AI-generated product marketing strategies."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.base import get_async_session_factory
from app.database.strategy_repository import StrategyRepository
from app.services.strategy.generator import ProductStrategyGenerator

router = APIRouter()


class GenerateRequest(BaseModel):
    product_id: int


@router.post("/strategy/generate")
async def strategy_generate(req: GenerateRequest) -> dict:
    """为指定商品生成运营方案。"""
    try:
        from app.services.product_service import ProductService

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            # 获取商品信息
            product_svc = ProductService(session)
            product = await product_svc.get_by_id(req.product_id)
            if product is None:
                raise HTTPException(status_code=404, detail="商品不存在")

            product_info = {
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "sales_24h": product.sales_24h,
                "trend_score": float(product.ai_score or 50),
                "lifecycle": product.lifecycle_stage,
                "knowledge_tags": [],
            }

            generator = ProductStrategyGenerator(session)
            return await generator.generate(product_info)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="生成运营方案失败")


@router.get("/strategy/{product_id}")
async def strategy_history(product_id: int) -> list[dict]:
    """获取指定商品的历史运营方案。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = StrategyRepository(session)
            records = await repo.get_history(product_id)
            if not records:
                raise HTTPException(status_code=404, detail="暂无运营方案")
            return [
                {
                    "id": r.id,
                    "product_id": r.product_id,
                    "title": r.title,
                    "selling_points": json.loads(r.selling_points) if r.selling_points else [],
                    "xiaohongshu_copy": r.xiaohongshu_copy,
                    "xianyu_copy": r.xianyu_copy,
                    "price_strategy": json.loads(r.price_strategy) if r.price_strategy else {},
                    "profit_analysis": json.loads(r.profit_analysis) if r.profit_analysis else {},
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="获取运营方案失败")
