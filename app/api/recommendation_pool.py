"""Recommendation Pool API — 推荐池查询 + 审核状态管理 + 发布 (Phase 46.2+46.4).

端点：
- GET  /recommendation-pool            → 推荐池列表（聚合查询）
- GET  /recommendation-pool/stats      → 审核状态统计
- GET  /recommendation-pool/{product_id} → 单条详情（含全部供应商匹配）
- PATCH /recommendation-pool/{product_id}/status → 更新审核状态
- POST /recommendation-pool/{product_id}/publish → 发布商品 (Phase 46.4)
- GET  /recommendation-pool/{product_id}/publish-history → 发布历史 (Phase 46.4)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database.base import get_async_session_factory
from app.models.recommendation_status import PoolStatus
from app.services.recommendation.pool_service import RecommendationPoolService

router = APIRouter()


# ── Request schema ──────────────────────────────────────────


class UpdateStatusRequest(BaseModel):
    """审核状态更新请求。report_date 不传则默认最新一期。"""

    status: PoolStatus  # FastAPI 自动校验枚举值
    notes: str | None = None
    report_date: str | None = None  # ISO 格式日期字符串


# ── GET /recommendation-pool ────────────────────────────────


@router.get("/recommendation-pool")
async def recommendation_pool(
    status: PoolStatus | None = Query(default=None, description="按审核状态筛选"),
    min_score: float | None = Query(default=None, ge=0.0, le=100.0, description="最低评分"),
    platform: str | None = Query(default=None, description="平台筛选"),
    report_date: str | None = Query(default=None, description="推荐日期 (YYYY-MM-DD)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """获取推荐池列表（live aggregation query）。

    数据来源：daily_report_items + products + supplier_matches(rank=1) + recommendation_status。
    无写操作，不修改任何业务数据。
    """
    from datetime import date as date_type

    try:
        rd = date_type.fromisoformat(report_date) if report_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="report_date 格式无效，请使用 YYYY-MM-DD")

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPoolService(session)
            return await svc.list_pool(
                report_date=rd,
                status=status,
                min_score=min_score,
                platform=platform,
                limit=limit,
                offset=offset,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取推荐池失败: {e}")


# ── GET /recommendation-pool/stats ──────────────────────────


@router.get("/recommendation-pool/stats")
async def recommendation_pool_stats(
    report_date: str | None = Query(default=None, description="推荐日期 (YYYY-MM-DD)"),
) -> dict:
    """推荐池审核状态统计。"""
    from datetime import date as date_type

    try:
        rd = date_type.fromisoformat(report_date) if report_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="report_date 格式无效，请使用 YYYY-MM-DD")

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPoolService(session)
            return await svc.stats(report_date=rd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取推荐池统计失败: {e}")


# ── GET /recommendation-pool/{product_id} ───────────────────


@router.get("/recommendation-pool/{product_id}")
async def recommendation_pool_detail(
    product_id: int,
    report_date: str | None = Query(default=None, description="推荐日期 (YYYY-MM-DD)"),
) -> dict:
    """获取单个推荐池条目详情（含全部 supplier_matches）。"""
    from datetime import date as date_type

    try:
        rd = date_type.fromisoformat(report_date) if report_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="report_date 格式无效，请使用 YYYY-MM-DD")

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPoolService(session)
            detail = await svc.get_pool_detail(product_id=product_id, report_date=rd)
            if detail is None:
                raise HTTPException(status_code=404, detail=f"商品 {product_id} 在推荐池中不存在")
            return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取推荐池详情失败: {e}")


# ── PATCH /recommendation-pool/{product_id}/status ──────────


@router.patch("/recommendation-pool/{product_id}/status")
async def update_pool_status(
    product_id: int,
    body: UpdateStatusRequest,
) -> dict:
    """更新推荐池商品的审核状态。

    - report_date 不传 → 默认最新一期 DailyReport.report_date
    - 状态流转受校验规则约束（非法流转返回 422）
    """
    from datetime import date as date_type

    rd: date_type | None = None
    if body.report_date:
        try:
            rd = date_type.fromisoformat(body.report_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="report_date 格式无效，请使用 YYYY-MM-DD")

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPoolService(session)
            return await svc.update_status(
                product_id=product_id,
                status=body.status,
                notes=body.notes,
                report_date=rd,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新审核状态失败: {e}")


# ── POST /recommendation-pool/{product_id}/publish ──────────


@router.post("/recommendation-pool/{product_id}/publish")
async def publish_product(
    product_id: int,
    platform: str = Query(default="taobao", description="目标平台"),
    report_date: str | None = Query(default=None, description="推荐日期 (YYYY-MM-DD)"),
) -> dict:
    """发布推荐商品（仅 APPROVED 状态可发布）。

    流程：
    - 校验状态 → 必须 APPROVED
    - 创建发布记录 → 模拟发布
    - 成功: status → PUBLISHED
    - 失败: status 保持 APPROVED
    """
    from datetime import date as date_type

    try:
        rd = date_type.fromisoformat(report_date) if report_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="report_date 格式无效，请使用 YYYY-MM-DD")

    from app.services.recommendation.publish_service import (
        RecommendationPublishService,
    )

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPublishService(session)
            result = await svc.publish(
                product_id=product_id,
                platform=platform,
                report_date=rd,
            )
            await session.commit()
            return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发布失败: {e}")


# ── GET /recommendation-pool/{product_id}/publish-history ───


@router.get("/recommendation-pool/{product_id}/publish-history")
async def publish_history(
    product_id: int,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """查询商品的发布历史记录。"""
    from app.services.recommendation.publish_service import (
        RecommendationPublishService,
    )

    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = RecommendationPublishService(session)
            records = await svc.get_publish_history(
                product_id=product_id, limit=limit
            )
            return {"product_id": product_id, "total": len(records), "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取发布历史失败: {e}")
