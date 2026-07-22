"""Taobao daily collect task — real integration (Phase 44.4.1.2).

将骨架连接到现有淘宝采集系统。流程::

    TaskContext
        │
    TaobaoCrawler.crawl_with_metrics()   # 采集新品（不重写爬虫）
        │
    ProductService.save_raw_products()   # 保存数据库（不改数据模型）
        │
    ctx.set_result({total, success, failed, duration})

约束：
- 不重写 TaobaoCrawler（仅调用其公开 crawl_with_metrics）
- 不修改登录系统（登录检测由 crawler 内部完成）
- 不修改数据模型（复用 ProductService / ProductRepository）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tasks.context import TaskContext


# ── Persistence helper ─────────────────────────────────────────


async def _save_products(products: list[Any]) -> dict[str, Any]:
    """将采集到的原始商品保存到数据库。

    复用 ProductService.save_raw_products（清洗 → upsert → 历史快照）。

    Args:
        products: RawProduct 列表。

    Returns:
        ProductService.save_raw_products 的统计字典。
    """
    from app.database.base import get_async_session_factory
    from app.services.product_service import ProductService

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        service = ProductService(session)
        return await service.save_raw_products(products)


# ── Core task function ─────────────────────────────────────────


async def taobao_daily_collect(ctx: TaskContext) -> None:
    """淘宝新品采集任务（真实流程）。

    通过 TaskContext 统一上下文接口运行：
    1. 读取配置关键词 / 限额
    2. 逐关键词调用 TaobaoCrawler.crawl_with_metrics 采集
    3. 汇总商品并保存数据库
    4. ctx.set_result({total, success, failed, duration})

    异常处理：
    - 单关键词采集失败 → 记录警告并继续其它关键词（弹性）
    - 保存或初始化等致命异常 → ctx.set_error() 记录，任务优雅结束

    Args:
        ctx: 任务运行上下文。
    """
    from app.config.settings import get_settings
    from app.config.scheduler import scheduler_settings
    from app.crawler.taobao import TaobaoCrawler

    ctx.log("淘宝新品采集任务开始")
    start = datetime.now(timezone.utc)

    settings = get_settings()
    keywords = list(settings.crawl_keywords)
    limit = settings.daily_crawl_limit
    max_pages = scheduler_settings.taobao_max_pages

    ctx.add_metadata("platform", "taobao")
    ctx.add_metadata("keywords", keywords)

    crawler = TaobaoCrawler()
    crawl_failures = 0

    try:
        # ── Step 1: 采集新品 ───────────────────────────────
        all_products: list[Any] = []
        for keyword in keywords:
            try:
                result = await crawler.crawl_with_metrics(
                    keyword=keyword,
                    max_pages=max_pages,
                    limit=limit,
                )
                products = result.products
                all_products.extend(products)
                ctx.log(f"关键词 '{keyword}' 采集到 {len(products)} 个商品")
            except Exception as exc:  # 单关键词失败不影响整体
                crawl_failures += 1
                ctx.log(f"关键词 '{keyword}' 采集失败: {exc}", level="WARNING")

        total = len(all_products)

        # ── Step 2: 保存数据库 ─────────────────────────────
        saved = 0
        if all_products:
            stats = await _save_products(all_products)
            saved = int(stats.get("saved_count", 0))
            ctx.add_metadata("save_stats", stats)

        failed = (total - saved) + crawl_failures
        duration = (datetime.now(timezone.utc) - start).total_seconds()

        ctx.set_result(
            {
                "total": total,
                "success": saved,
                "failed": failed,
                "duration": round(duration, 2),
            }
        )
    except Exception as exc:  # 致命异常：优雅记录
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        ctx.add_metadata("duration", round(duration, 2))
        ctx.set_error(exc)
    finally:
        try:
            await crawler.close()
        except Exception as close_exc:  # 关闭失败不影响结果
            ctx.log(f"关闭爬虫失败: {close_exc}", level="WARNING")


# ── Registry integration ───────────────────────────────────────


def register_taobao_collect_task(registry: Any) -> Any:
    """将 taobao_daily_collect 注册到 TaskRegistry。

    包装流程：
    1. 创建 TaskContext
    2. 用 TaskExecutionLogger 记录执行（RUNNING → SUCCESS/FAILED）
    3. 返回 ctx.to_dict() 作为执行结果

    调度策略：cron，每天 02:00。任务名保持 ``taobao_daily_collect`` 不变。

    Args:
        registry: TaskRegistry 实例。

    Returns:
        注册的 TaskDefinition。
    """
    from app.config.scheduler import scheduler_settings
    from app.tasks.execution_logger import TaskExecutionLogger

    execution_logger = TaskExecutionLogger()

    async def _taobao_collect_wrapped() -> dict[str, Any]:
        """带执行日志与上下文的包装函数。"""

        async def _run() -> dict[str, Any]:
            ctx = TaskContext(task_name="taobao_daily_collect")
            await taobao_daily_collect(ctx)
            return ctx.to_dict()

        return await execution_logger.execute(
            "taobao_daily_collect",
            _run,
        )

    return registry.register(
        name="taobao_daily_collect",
        func=_taobao_collect_wrapped,
        trigger="cron",
        hour=scheduler_settings.taobao_collect_hour,
        minute=scheduler_settings.taobao_collect_minute,
    )
