"""System monitoring API endpoints — health check and system status."""

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.database.base import get_async_session_factory

router = APIRouter()

# ── Runtime toggle for daily selection ────────────────────
# Initialised from settings at startup; mutable at runtime via /toggle API.

_selection_enabled: bool | None = None  # lazy-init on first access


def _get_selection_enabled() -> bool:
    """Return current selection-enabled state, lazy-initing from settings."""
    global _selection_enabled
    if _selection_enabled is None:
        from app.config.settings import get_settings
        _selection_enabled = get_settings().daily_selection_enabled
    return _selection_enabled


def _set_selection_enabled(value: bool) -> None:
    """Update the runtime flag and sync the scheduler job."""
    global _selection_enabled
    from app.api.main import _scheduler_instance

    _selection_enabled = value
    if _scheduler_instance is not None:
        if value:
            _scheduler_instance.add_daily_selection()
            logger.info("[API] 自动选品已开启 — daily_selection_job 已注册")
        else:
            _scheduler_instance.remove_job("daily_selection")
            logger.info("[API] 自动选品已关闭 — daily_selection_job 已移除")


# ── Request model ──────────────────────────────────────────

class SelectionToggleRequest(BaseModel):
    enabled: bool


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


# ── AI 自动选品开关 ──────────────────────────────────────

@router.get("/system/selection/status")
async def selection_status() -> dict:
    """返回 AI 自动选品开关状态。

    Returns:
        {"enabled": true} 或 {"enabled": false}
    """
    return {"enabled": _get_selection_enabled()}


@router.post("/system/selection/toggle")
async def selection_toggle(body: SelectionToggleRequest) -> dict:
    """开启或关闭 AI 自动选品。

    Body:
        {"enabled": true}  — 开启
        {"enabled": false} — 关闭

    Returns:
        {"enabled": true, "message": "..."}
    """
    _set_selection_enabled(body.enabled)
    state = "已开启" if body.enabled else "已关闭"
    return {"enabled": body.enabled, "message": f"AI 自动选品{state}"}
