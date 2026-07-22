"""TaskRegistry — business task registration layer (Phase 44.2).

Sits between SchedulerManager and concrete business jobs.
Stores task *definitions* (name / func / trigger / kwargs) and
delegates actual scheduling to SchedulerManager.

Layering::

    TaskRegistry   ← this module (WHAT to run)
        │
    SchedulerManager  ← app/scheduler/ (HOW to schedule)
        │
    APScheduler    ← library (WHEN to fire)

This module is business-logic-free — no crawl, match, or report logic.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from loguru import logger


class TaskDefinition:
    """描述一个已注册的业务任务（纯数据对象）。"""

    __slots__ = ("name", "func", "trigger", "trigger_kwargs", "enabled")

    def __init__(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        trigger: Any = "date",
        enabled: bool = True,
        **trigger_kwargs: Any,
    ) -> None:
        self.name = name
        self.func = func
        self.trigger = trigger
        self.trigger_kwargs = trigger_kwargs
        self.enabled = enabled

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（用于 API 返回）。"""
        return {
            "name": self.name,
            "func": getattr(self.func, "__name__", str(self.func)),
            "trigger": str(self.trigger),
            "trigger_kwargs": self.trigger_kwargs,
            "enabled": self.enabled,
        }


class TaskRegistry:
    """业务任务注册中心。

    职责：
    - register(name, func, trigger, **kwargs): 注册任务定义
    - unregister(name): 注销任务
    - get_task(name): 获取单个任务定义
    - list_tasks(): 列出所有已注册任务
    - sync_to_scheduler(mgr): 将所有已注册任务同步到 SchedulerManager

    不负责调度本身 — 调度由 SchedulerManager 完成。

    Usage::

        registry = TaskRegistry()
        registry.register("daily_report", gen_report, trigger="cron", hour=8)
        registry.sync_to_scheduler(scheduler_manager)
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskDefinition] = {}

    # ── Registration ──────────────────────────────────────────

    def register(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        trigger: Any = "date",
        *,
        enabled: bool = True,
        **trigger_kwargs: Any,
    ) -> TaskDefinition:
        """注册一个业务任务。

        如果同名任务已存在，则覆盖（幂等注册）。

        Args:
            name: 任务唯一名称（同时作为 scheduler job_id）。
            func: async 协程函数。
            trigger: APScheduler trigger 实例或类型字符串。
            enabled: 是否启用（False 时 sync 跳过）。
            **trigger_kwargs: 传递给 trigger 的参数。

        Returns:
            注册的 TaskDefinition。
        """
        definition = TaskDefinition(
            name=name,
            func=func,
            trigger=trigger,
            enabled=enabled,
            **trigger_kwargs,
        )
        is_update = name in self._tasks
        self._tasks[name] = definition

        if is_update:
            logger.info("[TaskRegistry] Updated task: {}", name)
        else:
            logger.info("[TaskRegistry] Registered task: {}", name)
        return definition

    def unregister(self, name: str) -> bool:
        """注销指定任务。

        Args:
            name: 任务名称。

        Returns:
            True 表示成功删除，False 表示任务不存在。
        """
        if name in self._tasks:
            del self._tasks[name]
            logger.info("[TaskRegistry] Unregistered task: {}", name)
            return True
        logger.warning("[TaskRegistry] Task not found: {}", name)
        return False

    # ── Query ─────────────────────────────────────────────────

    def get_task(self, name: str) -> TaskDefinition | None:
        """获取指定任务的完整定义。

        Args:
            name: 任务名称。

        Returns:
            TaskDefinition 或 None。
        """
        return self._tasks.get(name)

    def list_tasks(self) -> list[dict[str, Any]]:
        """列出所有已注册任务（摘要）。"""
        return [d.to_dict() for d in self._tasks.values()]

    def list_enabled_tasks(self) -> list[TaskDefinition]:
        """列出所有启用的任务定义。"""
        return [d for d in self._tasks.values() if d.enabled]

    @property
    def task_count(self) -> int:
        """已注册任务总数。"""
        return len(self._tasks)

    # ── Scheduler sync ────────────────────────────────────────

    def sync_to_scheduler(self, scheduler: Any) -> int:
        """将所有已启用任务同步到 SchedulerManager。

        遍历 self._tasks 中所有 enabled=True 的定义，
        调用 scheduler.add_job() 注册到 APScheduler。

        Args:
            scheduler: SchedulerManager 实例。

        Returns:
            成功同步的任务数量。
        """
        count = 0
        for definition in self.list_enabled_tasks():
            try:
                scheduler.add_job(
                    func=definition.func,
                    trigger=definition.trigger,
                    job_id=definition.name,
                    name=definition.name,
                    **definition.trigger_kwargs,
                )
                count += 1
            except Exception as e:
                logger.error(
                    "[TaskRegistry] Failed to sync task '{}': {}",
                    definition.name, e,
                )
        logger.info("[TaskRegistry] Synced {} task(s) to scheduler", count)
        return count

    def remove_from_scheduler(self, scheduler: Any, name: str) -> bool:
        """从 SchedulerManager 中移除指定任务。

        Args:
            scheduler: SchedulerManager 实例。
            name: 任务名称。

        Returns:
            True 表示成功移除。
        """
        return scheduler.remove_job(name)
