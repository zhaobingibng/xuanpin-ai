"""Task bootstrap — 集中注册 Phase 44 定时任务 (Phase 45.2).

将四个 Phase 44 业务任务统一注册到 TaskRegistry，并同步到运行中的
SchedulerManager，形成完整调度闭环::

    build_task_registry()          # 汇总所有 register_*_task
        │
    TaskRegistry (WHAT)            # 任务定义层
        │
    registry.sync_to_scheduler()   # 同步
        │
    SchedulerManager (HOW)         # APScheduler 执行调度层

约束：
- 复用现有 register_*_task / TaskRegistry / SchedulerManager / TaskExecutionLogger
- 不新增框架、不新增抽象层、不修改任务业务逻辑
- 唯一职责：集中登记 + 同步，无任何采集/匹配/推荐逻辑

已登记任务（cron，每天）：
    system_health_check   01:00
    taobao_daily_collect  02:00
    supplier_matching     04:00
    daily_recommendation  06:00
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.tasks.registry import TaskRegistry


def build_task_registry(scheduler_manager: Any = None) -> TaskRegistry:
    """创建 TaskRegistry 并登记所有 Phase 44 业务任务。

    仅做登记，不做调度同步（同步由 bootstrap_tasks / 调用方负责）。

    Args:
        scheduler_manager: 可选 SchedulerManager，透传给健康检查任务
            用于调度器运行状态自检（其余任务不需要）。

    Returns:
        已登记全部任务的 TaskRegistry 实例。
    """
    from app.tasks.health_check_task import register_health_check_task
    from app.tasks.recommendation_task import register_recommendation_task
    from app.tasks.supplier_matching_task import register_supplier_matching_task
    from app.tasks.taobao_collect_task import register_taobao_collect_task

    registry = TaskRegistry()

    register_health_check_task(registry, scheduler_manager=scheduler_manager)
    register_taobao_collect_task(registry)
    register_supplier_matching_task(registry)
    register_recommendation_task(registry)

    logger.info(
        "[TaskBootstrap] Registered {} Phase 44 task(s)", registry.task_count
    )
    return registry


def bootstrap_tasks(scheduler_manager: Any) -> tuple[TaskRegistry, int]:
    """构建 registry 并同步到 SchedulerManager。

    Args:
        scheduler_manager: 目标 SchedulerManager 实例。

    Returns:
        (registry, synced_count) —— 已登记的 registry 与成功同步的任务数。
    """
    registry = build_task_registry(scheduler_manager=scheduler_manager)
    synced = registry.sync_to_scheduler(scheduler_manager)
    logger.info("[TaskBootstrap] Synced {} task(s) to scheduler", synced)
    return registry, synced
