"""Supplier matching task — 1688 自动匹配 (Phase 44.5).

将淘宝新品自动匹配到 1688 供应链，接入 Phase 44 自动化框架::

    TaskContext
        │
    ProductRepository.find_new_products()          # 取待匹配新品
        │
    SupplierMatchingService.match_products_with_matcher()  # 复用现有匹配服务
        │
    session.add(SupplierMatch) + commit            # 持久化匹配记录
        │
    ctx.set_result({total, matched, failed, duration})

约束：
- 复用现有 SupplierMatchingService / SupplierProductRepository / ProductRepository
- 不新增框架、不新增抽象层、不修改匹配算法与数据模型
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tasks.context import TaskContext


# ── Core task function ─────────────────────────────────────────


async def supplier_matching_task(ctx: TaskContext) -> None:
    """1688 供应链自动匹配任务。

    流程：
    1. 读取配置匹配限额
    2. 取待匹配的新品（lifecycle_stage=NEW）
    3. 逐商品调用 SupplierMatchingService.match_products_with_matcher 匹配
    4. 保存 SupplierMatch 记录
    5. ctx.set_result({total, matched, failed, duration})

    异常处理：
    - 单商品匹配失败 → 记录警告并继续（弹性）
    - 会话/提交等致命异常 → ctx.set_error() 记录，任务优雅结束

    Args:
        ctx: 任务运行上下文。
    """
    from app.config.settings import get_settings
    from app.config.scheduler import scheduler_settings
    from app.database.base import get_async_session_factory
    from app.database.product_repository import ProductRepository
    from app.services.supplier_matching import SupplierMatchingService

    ctx.log("1688供应链匹配任务开始")
    start = datetime.now(timezone.utc)

    settings = get_settings()
    limit = settings.daily_crawl_limit
    top_k = scheduler_settings.matching_top_k

    ctx.add_metadata("top_k", top_k)

    service = SupplierMatchingService()
    session_factory = get_async_session_factory()

    total = 0
    matched = 0
    failed = 0

    try:
        async with session_factory() as session:
            repo = ProductRepository(session)
            products = await repo.find_new_products(limit=limit)
            total = len(products)
            ctx.log(f"待匹配新品数量: {total}")

            for product in products:
                try:
                    matches = await service.match_products_with_matcher(
                        session, product, top_k=top_k,
                    )
                    if matches:
                        for m in matches:
                            session.add(m)
                        matched += 1
                except Exception as exc:  # 单商品失败不影响整体
                    failed += 1
                    ctx.log(
                        f"匹配失败 product_id={getattr(product, 'id', None)}: {exc}",
                        level="WARNING",
                    )

            await session.commit()

        duration = (datetime.now(timezone.utc) - start).total_seconds()
        ctx.set_result(
            {
                "total": total,
                "matched": matched,
                "failed": failed,
                "duration": round(duration, 2),
            }
        )
    except Exception as exc:  # 致命异常：优雅记录
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        ctx.add_metadata("duration", round(duration, 2))
        ctx.set_error(exc)


# ── Registry integration ───────────────────────────────────────


def register_supplier_matching_task(registry: Any) -> Any:
    """将 supplier_matching_task 注册到 TaskRegistry。

    包装流程：
    1. 创建 TaskContext
    2. 用 TaskExecutionLogger 记录执行（RUNNING → SUCCESS/FAILED）
    3. 返回 ctx.to_dict() 作为执行结果

    调度策略：cron，每天 04:00。

    Args:
        registry: TaskRegistry 实例。

    Returns:
        注册的 TaskDefinition。
    """
    from app.config.scheduler import scheduler_settings
    from app.tasks.execution_logger import TaskExecutionLogger

    execution_logger = TaskExecutionLogger()

    async def _supplier_matching_wrapped() -> dict[str, Any]:
        """带执行日志与上下文的包装函数。"""

        async def _run() -> dict[str, Any]:
            ctx = TaskContext(task_name="supplier_matching")
            await supplier_matching_task(ctx)
            return ctx.to_dict()

        return await execution_logger.execute(
            "supplier_matching",
            _run,
        )

    return registry.register(
        name="supplier_matching",
        func=_supplier_matching_wrapped,
        trigger="cron",
        hour=scheduler_settings.supplier_matching_hour,
        minute=scheduler_settings.supplier_matching_minute,
    )
