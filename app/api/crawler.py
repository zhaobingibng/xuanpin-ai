"""Crawler API endpoints — status and logs."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory
from app.database.crawler_status_repository import CrawlerStatusRepository
from app.database.crawl_log_repository import CrawlLogRepository

router = APIRouter()


@router.get("/crawler/status")
async def crawler_status() -> list[dict]:
    """获取最近的采集状态记录。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = CrawlerStatusRepository(session)
            records = await repo.get_latest(limit=10)
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


@router.get("/crawler/logs")
async def crawler_logs(limit: int = 20, platform: str | None = None) -> list[dict]:
    """获取历史采集日志记录。

    Args:
        limit: 最多返回条数，默认 20。
        platform: 可选平台过滤。
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = CrawlLogRepository(session)
            records = await repo.get_logs(limit=limit, platform=platform)
            return [
                {
                    "id": r.id,
                    "keyword": r.keyword,
                    "platform": r.platform,
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "total": r.total,
                    "success": r.success,
                    "failed": r.failed,
                    "status": r.status,
                    "error": r.error,
                }
                for r in records
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取采集日志失败")
