"""Dashboard API endpoints — operations management statistics.

Phase 42.6: 新增淘宝人工辅助采集端点。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database.base import get_async_session_factory
from app.database.crawler_status_repository import CrawlerStatusRepository
from app.services.dashboard.service import DashboardService

router = APIRouter()


# ── Request models (Phase 42.6) ──────────────────────────────

class TaobaoCrawlRequest(BaseModel):
    keyword: str = "海苔卷"
    limit: int = 10


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


@router.get("/dashboard/home")
async def dashboard_home(limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """首页运行概览（今日概览/最近一次任务/高分商品/供应链匹配）。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return await svc.home_summary(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取首页概览失败: {e}")


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


# ═══════════════════════════════════════════════════════════════
# Phase 42.6 — 淘宝人工辅助采集
# ═══════════════════════════════════════════════════════════════


@router.get("/dashboard/taobao/status")
async def taobao_session_status() -> dict:
    """获取淘宝浏览器会话状态。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    info = svc.get_snapshot()

    # 附带商品总数
    product_count = 0
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT COUNT(*) FROM products WHERE platform = 'taobao'"))
            product_count = result.scalar() or 0
    except Exception:
        pass

    return {
        "state": info.state.value,
        "is_logged_in": info.is_logged_in,
        "is_blocked": info.is_blocked,
        "block_reason": info.block_reason,
        "last_check": info.last_check.isoformat() if info.last_check else None,
        "last_crawl": info.last_crawl.isoformat() if info.last_crawl else None,
        "last_crawl_keyword": info.last_crawl_keyword,
        "last_crawl_count": info.last_crawl_count,
        "session_started": info.session_started.isoformat() if info.session_started else None,
        "message": info.message,
        "product_count": product_count,
    }


@router.post("/dashboard/taobao/start")
async def taobao_session_start() -> dict:
    """启动淘宝浏览器会话。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    info = await svc.start_session()

    return {
        "state": info.state.value,
        "is_logged_in": info.is_logged_in,
        "is_blocked": info.is_blocked,
        "block_reason": info.block_reason,
        "message": info.message,
        "session_started": info.session_started.isoformat() if info.session_started else None,
    }


@router.post("/dashboard/taobao/stop")
async def taobao_session_stop() -> dict:
    """关闭淘宝浏览器会话。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    info = await svc.stop_session()

    return {
        "state": info.state.value,
        "message": info.message,
    }


@router.post("/dashboard/taobao/check")
async def taobao_session_check() -> dict:
    """重新检测登录/风控状态。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    info = await svc.check_status()

    return {
        "state": info.state.value,
        "is_logged_in": info.is_logged_in,
        "is_blocked": info.is_blocked,
        "block_reason": info.block_reason,
        "message": info.message,
    }


@router.post("/dashboard/taobao/crawl")
async def taobao_session_crawl(req: TaobaoCrawlRequest) -> dict:
    """触发淘宝关键词采集（需先启动会话）。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    result = await svc.crawl(keyword=req.keyword, limit=req.limit)

    return result


@router.post("/dashboard/taobao/wait-human")
async def taobao_session_wait_human() -> dict:
    """等待人工解除风控（轮询检测，最长5分钟）。"""
    from app.services.taobao_session_service import get_taobao_session

    svc = get_taobao_session()
    info = await svc.wait_for_human(poll_interval=3.0, max_wait=300.0)

    return {
        "state": info.state.value,
        "is_blocked": info.is_blocked,
        "message": info.message,
    }


# ═══════════════════════════════════════════════════════════════
# Phase 45.3 — 定时任务管理（复用 TaskRegistry / SchedulerManager /
#              TaskExecutionRepository，手动执行走 TaskDefinition.func()）
# ═══════════════════════════════════════════════════════════════


@router.get("/dashboard/tasks/definitions")
async def dashboard_task_definitions() -> list[dict]:
    """获取所有已注册任务定义（TaskRegistry.list_tasks）。

    调度未就绪（registry 未初始化）时返回空列表。
    """
    from app.api import main

    registry = main._task_registry
    if registry is None:
        return []
    return registry.list_tasks()


@router.get("/dashboard/scheduler/jobs")
async def dashboard_scheduler_jobs() -> list[dict]:
    """获取调度器当前任务状态（SchedulerManager.get_jobs）。

    调度未就绪时返回空列表。
    """
    from app.api import main

    mgr = main._scheduler_manager
    if mgr is None:
        return []
    return mgr.get_jobs()


@router.get("/dashboard/tasks/{name}/history")
async def dashboard_task_history(
    name: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """获取指定任务的执行历史（DashboardService → TaskExecutionRepository）。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DashboardService(session)
            return await svc.get_task_history(name, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务执行历史失败: {e}")


@router.post("/dashboard/tasks/{name}/run")
async def dashboard_task_run(name: str) -> dict:
    """手动执行指定任务。

    严格走 TaskDefinition.func() —— 该包装已内置 TaskExecutionLogger，
    因此手动触发与定时触发共用同一执行路径，不绕过执行日志。
    """
    from app.api import main

    registry = main._task_registry
    if registry is None:
        raise HTTPException(status_code=503, detail="任务调度未就绪")

    td = registry.get_task(name)
    if td is None:
        raise HTTPException(status_code=404, detail=f"任务 {name} 不存在")

    try:
        result = await td.func()
        return {"success": True, "task_name": name, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行任务失败: {e}")

