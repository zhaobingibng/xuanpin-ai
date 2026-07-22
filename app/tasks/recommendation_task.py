"""Daily recommendation task — 自动推荐 (Phase 44.6).

将每日推荐生成接入 Phase 44 自动化框架::

    TaskContext
        │
    DailyRecommendationService.generate()   # 复用现有推荐流程（评分→排序→保存）
        │
    ctx.set_result({total, recommended, failed, duration})

约束：
- 复用现有 DailyRecommendationService / RecommendationRepository
- 不新增框架、不新增抽象层、不修改 Service
- 与 taobao_daily_collect / supplier_matching 保持相同风格
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tasks.context import TaskContext


# ── Core task function ─────────────────────────────────────────


async def recommendation_task(ctx: TaskContext) -> None:
    """每日自动推荐任务。

    流程：
    1. 打开会话，构造 DailyRecommendationService
    2. 调用 generate() 完成 评分→排序→保存
    3. ctx.set_result({total, recommended, failed, duration})

    异常处理：
    - 生成/会话等致命异常 → ctx.set_error() 记录，任务优雅结束

    Args:
        ctx: 任务运行上下文。
    """
    from app.database.base import get_async_session_factory
    from app.services.recommendation.daily_recommendation import (
        DailyRecommendationService,
    )

    ctx.log("每日推荐任务开始")
    start = datetime.now(timezone.utc)

    session_factory = get_async_session_factory()

    try:
        async with session_factory() as session:
            service = DailyRecommendationService(session)
            report = await service.generate()

            # Phase 46.3: 同步推荐结果到推荐池
            from datetime import date as dt_date

            from app.services.recommendation.pool_initializer import (
                RecommendationPoolInitializer,
            )

            report_date_str = report.get("date", dt_date.today().isoformat())
            sync_date = dt_date.fromisoformat(report_date_str)
            try:
                init = RecommendationPoolInitializer(session)
                init_result = await init.sync(sync_date)
                ctx.log(f"推荐池同步: synced={init_result['synced']}, skipped={init_result['skipped']}")
            except Exception as sync_err:
                ctx.log(f"推荐池同步失败（不影响推荐结果）: {sync_err}")

        total = int(report.get("total", 0))
        recommended = len(report.get("items", []))
        failed = max(total - recommended, 0)
        duration = (datetime.now(timezone.utc) - start).total_seconds()

        ctx.add_metadata("date", report.get("date"))
        ctx.log(f"推荐生成完成: total={total}, recommended={recommended}")
        ctx.set_result(
            {
                "total": total,
                "recommended": recommended,
                "failed": failed,
                "duration": round(duration, 2),
            }
        )
    except Exception as exc:  # 致命异常：优雅记录
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        ctx.add_metadata("duration", round(duration, 2))
        ctx.set_error(exc)


# ── Registry integration ───────────────────────────────────────


def register_recommendation_task(registry: Any) -> Any:
    """将 recommendation_task 注册到 TaskRegistry。

    包装流程：
    1. 创建 TaskContext
    2. 用 TaskExecutionLogger 记录执行（RUNNING → SUCCESS/FAILED）
    3. 返回 ctx.to_dict() 作为执行结果

    调度策略：cron，每天 06:00。

    Args:
        registry: TaskRegistry 实例。

    Returns:
        注册的 TaskDefinition。
    """
    from app.config.scheduler import scheduler_settings
    from app.tasks.execution_logger import TaskExecutionLogger

    execution_logger = TaskExecutionLogger()

    async def _recommendation_wrapped() -> dict[str, Any]:
        """带执行日志与上下文的包装函数。"""

        async def _run() -> dict[str, Any]:
            ctx = TaskContext(task_name="daily_recommendation")
            await recommendation_task(ctx)
            return ctx.to_dict()

        return await execution_logger.execute(
            "daily_recommendation",
            _run,
        )

    return registry.register(
        name="daily_recommendation",
        func=_recommendation_wrapped,
        trigger="cron",
        hour=scheduler_settings.daily_recommendation_hour,
        minute=scheduler_settings.daily_recommendation_minute,
    )
