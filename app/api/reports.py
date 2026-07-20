"""Daily report API endpoints."""

import json

from fastapi import APIRouter, HTTPException

from app.api.schemas.report import (
    DailyReportResponse,
    ReportDetailItem,
    ReportDetailResponse,
    ReportSummary,
)
from app.database.base import get_async_session_factory
from app.database.lifecycle_repository import LifecycleRepository
from app.database.report_repository import ReportRepository
from app.services.report.daily_report import DailyReportService

router = APIRouter()


@router.get("/reports/daily", response_model=DailyReportResponse)
async def daily_report(limit: int = 20) -> dict:
    """生成每日选品报告。

    Args:
        limit: 返回商品数量的上限，默认 20。

    Returns:
        DailyReportResponse 结构的字典。

    Raises:
        HTTPException: 服务异常时返回 500。
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyReportService(session)
            report = await svc.generate(limit=limit)
            return report
    except Exception:
        raise HTTPException(status_code=500, detail="生成日报失败")


@router.get("/reports/history", response_model=list[ReportSummary])
async def report_history(limit: int = 30) -> list[dict]:
    """获取历史日报列表。

    Args:
        limit: 返回条数上限，默认 30。

    Returns:
        按日期降序的日报摘要列表。
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ReportRepository(session)
            reports = await repo.get_history(limit=limit)
            return [
                {
                    "id": r.id,
                    "report_date": r.report_date.isoformat(),
                    "total": r.total,
                    "hot_products": r.hot_products,
                    "potential_products": r.potential_products,
                    "average_score": r.average_score,
                }
                for r in reports
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取历史日报失败")


@router.get("/reports/lifecycle/hot")
async def lifecycle_hot() -> list[dict]:
    """获取当前 HOT（持续热门）商品列表。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = LifecycleRepository(session)
            products = await repo.get_hot_products()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "platform": p.platform,
                    "price": p.price,
                    "sales_24h": p.sales_24h,
                    "viewers": p.viewers,
                    "lifecycle_stage": p.lifecycle_stage,
                }
                for p in products
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取热门商品失败")


@router.get("/reports/lifecycle/rising")
async def lifecycle_rising() -> list[dict]:
    """获取当前 RISING（上涨中）商品列表。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = LifecycleRepository(session)
            products = await repo.get_rising_products()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "platform": p.platform,
                    "price": p.price,
                    "sales_24h": p.sales_24h,
                    "viewers": p.viewers,
                    "lifecycle_stage": p.lifecycle_stage,
                }
                for p in products
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取上涨商品失败")


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def report_detail(report_id: int) -> dict:
    """获取指定日报的详情。

    Args:
        report_id: 日报 ID。

    Returns:
        日报详情，包含所有商品条目。

    Raises:
        HTTPException: 404 if not found, 500 on error.
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ReportRepository(session)
            report = await repo.get_report_detail(report_id)
            if report is None:
                raise HTTPException(status_code=404, detail="日报不存在")

            items: list[dict] = []
            for item in sorted(report.items, key=lambda x: x.rank):
                try:
                    reasons = json.loads(item.reasons) if item.reasons else []
                except (json.JSONDecodeError, TypeError):
                    reasons = []
                items.append({
                    "id": item.id,
                    "product_id": item.product_id,
                    "rank": item.rank,
                    "name": item.name,
                    "platform": item.platform,
                    "image": item.image,
                    "price": item.price,
                    "score": item.score,
                    "level": item.level,
                    "reasons": reasons,
                })

            return {
                "id": report.id,
                "report_date": report.report_date.isoformat(),
                "total": report.total,
                "hot_products": report.hot_products,
                "potential_products": report.potential_products,
                "average_score": report.average_score,
                "items": items,
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="获取日报详情失败")
