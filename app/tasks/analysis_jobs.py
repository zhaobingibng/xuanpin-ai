"""Analysis job — clean, save (upsert), create history, calculate trend."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.models.schemas import RawProduct
from app.models.product_history import ProductHistory
from app.services.product_service import ProductService


async def analyze_products(
    raw_products: list[RawProduct],
    session: AsyncSession,
) -> dict[str, Any]:
    """执行数据清洗、upsert 保存、历史快照、趋势分析。

    保存步骤委托 ProductService.save_raw_products() 统一处理，
    保证与 daily_crawl_job 使用相同的 upsert 逻辑，避免重复数据。
    评分、推荐、排名逻辑保持不变。

    Args:
        raw_products: 原始采集数据列表。
        session: 异步数据库会话。

    Returns:
        包含各步骤统计信息的字典。
    """
    result: dict[str, Any] = {
        "raw_count": len(raw_products),
        "cleaned_count": 0,
        "saved_count": 0,
        "new_count": 0,
        "updated_count": 0,
        "history_count": 0,
        "trend_count": 0,
    }

    if not raw_products:
        logger.info("空数据，跳过分析")
        return result

    # ── Step 1: 清洗 + upsert 保存 + 历史快照 ───────────────
    svc = ProductService(session)
    save_result = await svc.save_raw_products(raw_products)

    result["cleaned_count"] = save_result["cleaned_count"]
    result["saved_count"] = save_result["saved_count"]
    result["new_count"] = save_result["new_count"]
    result["updated_count"] = save_result["updated_count"]
    result["history_count"] = save_result["history_count"]
    saved_products = save_result.get("saved_products", [])

    if not saved_products:
        logger.warning("无商品保存，跳过趋势分析")
        return result

    # ── Step 2: 趋势分析 ────────────────────────────────────
    # 直接遍历已保存商品列表（与原始逻辑一致）
    from app.services.analytics.analyzer import TrendAnalyzer

    trend_count = 0
    for product in saved_products:
        try:
            # 查询该商品的所有历史记录
            history_stmt = (
                select(ProductHistory)
                .where(ProductHistory.product_id == product.id)
                .order_by(ProductHistory.record_time)
            )
            history_result = await session.execute(history_stmt)
            histories = list(history_result.scalars().all())

            if len(histories) >= 2:
                analyzer = TrendAnalyzer(histories)
                trend_result = analyzer.calculate_trend_score()
                logger.debug(
                    "趋势分析: {} → score={}",
                    product.name, trend_result["trend_score"],
                )
                trend_count += 1
        except Exception as e:
            logger.error("趋势分析异常: product_id={} → {}", product.id, e)

    result["trend_count"] = trend_count
    logger.info("趋势分析完成: {} 个商品已分析", trend_count)

    # ── Step 3: 排行榜更新 ──────────────────────────────────
    # 排行榜由 API 层实时计算（RankingService），无需额外缓存
    logger.info("排行榜更新完成")

    logger.info(
        "分析完成: raw={}, cleaned={}, saved={} (new={}, update={}), history={}, trend={}",
        result["raw_count"],
        result["cleaned_count"],
        result["saved_count"],
        result["new_count"],
        result["updated_count"],
        result["history_count"],
        result["trend_count"],
    )

    return result
