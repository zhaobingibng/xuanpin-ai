"""Dashboard API endpoints — operations management statistics."""

from fastapi import APIRouter, HTTPException, Query

from app.database.base import get_async_session_factory
from app.database.crawler_status_repository import CrawlerStatusRepository
from app.services.dashboard.service import DashboardService

router = APIRouter()


@router.get("/dashboard/overview")
async def dashboard_overview() -> dict:
    """系统总览数据（业务统计）。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return await svc.overview()
    except Exception:
        raise HTTPException(status_code=500, detail="获取系统总览失败")


@router.get("/dashboard/system")
async def dashboard_system() -> dict:
    """系统运维总览数据（健康状态、任务统计、爬虫/调度器状态）。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return await svc.system_overview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统运维总览失败: {e}")


@router.get("/dashboard/tasks")
async def dashboard_tasks(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    """最近任务执行记录。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return await svc.get_recent_tasks(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务记录失败: {e}")


@router.get("/dashboard/notifications")
async def dashboard_notifications(limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    """通知历史记录。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return svc.get_notifications(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取通知历史失败: {e}")


@router.get("/dashboard/logs")
async def dashboard_logs(
    file: str = Query(default="app.log", pattern="^(app|error|crawler)\\.log$"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[str]:
    """读取日志文件。

    Args:
        file: 日志文件名 (app.log, error.log, crawler.log)
        limit: 返回行数限制
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return svc.get_logs(log_file=file, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志文件失败: {e}")


@router.get("/dashboard/crawler-status")
async def crawler_status(limit: int = 10) -> list[dict]:
    """最近采集状态列表。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = CrawlerStatusRepository(session)
            records = await repo.get_latest(limit=limit)
            return [
                {
                    "id": r.id,
                    "platform": r.platform,
                    "last_run_time": r.last_run_time.isoformat() if r.last_run_time else None,
                    "status": r.status,
                    "total": r.total,
                    "success": r.success,
                    "failed": r.failed,
                    "message": r.message,
                }
                for r in records
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取采集状态失败")
