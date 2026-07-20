"""Tasks API — failed task management endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.database.base import get_async_session_factory
from app.services.task_queue.service import TaskQueueService

router = APIRouter(tags=["tasks"])


@router.get("/tasks/failed")
async def get_failed_tasks(
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """获取失败任务列表。

    Args:
        status: 按状态筛选 (PENDING/RETRYING/FAILED/RESOLVED)
        limit: 返回数量限制
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = TaskQueueService(session)
            tasks = await svc.get_failed_tasks(status=status, limit=limit)
            return [
                {
                    "id": t.id,
                    "task_name": t.task_name,
                    "payload": t.payload,
                    "error": t.error,
                    "exception_type": t.exception_type,
                    "retry_count": t.retry_count,
                    "max_retry": t.max_retry,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in tasks
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取失败任务列表失败: {e}")


@router.get("/tasks/{task_id}")
async def get_failed_task(task_id: int) -> dict:
    """获取单个失败任务详情。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = TaskQueueService(session)
            task = await svc.get_task(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
            return {
                "id": task.id,
                "task_name": task.task_name,
                "payload": task.payload,
                "error": task.error,
                "exception_type": task.exception_type,
                "retry_count": task.retry_count,
                "max_retry": task.max_retry,
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {e}")


@router.post("/tasks/{task_id}/retry")
async def retry_failed_task(task_id: int) -> dict:
    """手动重试失败任务。

    Note: This endpoint requires the task to have a registered retry handler.
    Currently, it only marks the task for retry. Actual retry execution
    should be handled by a background worker or scheduler.
    """
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = TaskQueueService(session)
            task = await svc.get_task(task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

            if not task.can_retry():
                raise HTTPException(
                    status_code=400,
                    detail=f"任务 {task_id} 无法重试 (status={task.status}, retry={task.retry_count}/{task.max_retry})",
                )

            # Mark for retry (actual execution handled elsewhere)
            from app.database.failed_task_repository import FailedTaskRepository
            from app.models.failed_task import STATUS_RETRYING

            repo = FailedTaskRepository(session)
            updated = await repo.mark_retrying(task_id)

            return {
                "message": f"任务 {task_id} 已标记为重试中",
                "task": {
                    "id": updated.id,
                    "status": updated.status,
                    "retry_count": updated.retry_count,
                },
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重试任务失败: {e}")
