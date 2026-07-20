"""System monitoring API endpoints — health check and system status."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory

router = APIRouter()


@router.get("/system/health")
async def system_health() -> dict:
    """系统健康检查。

    Returns:
        {
            status: "healthy" | "warning" | "error",
            database: bool,
            crawler: bool,
            scheduler: bool,
            last_crawl: str | None,
        }
    """
    try:
        from app.services.health.service import HealthService

        # Check if scheduler is running
        from app.api.main import _scheduler_instance
        scheduler_running = (
            _scheduler_instance is not None and _scheduler_instance.running
        )

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = HealthService(session, scheduler_running=scheduler_running)
            return await svc.check()
    except Exception:
        raise HTTPException(status_code=500, detail="健康检查失败")
