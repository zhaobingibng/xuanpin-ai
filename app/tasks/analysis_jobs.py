"""Analysis job — clean, save, create history, calculate trend, update ranking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawler.models.schemas import RawProduct
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.cleaner.pipeline import CleanedProduct, ProductCleanPipeline


async def analyze_products(
    raw_products: list[RawProduct],
    session: AsyncSession,
) -> dict[str, Any]:
    """执行数据清洗、保存、历史快照、趋势分析。

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
        "history_count": 0,
        "trend_count": 0,
    }

    if not raw_products:
        logger.info("空数据，跳过分析")
        return result

    # ── Step 1: 清洗 ────────────────────────────────────────────
    logger.info("清洗数量…")
    pipeline = ProductCleanPipeline()
    cleaned: list[CleanedProduct] = pipeline.process_batch(raw_products)
    result["cleaned_count"] = len(cleaned)
    logger.info("清洗数量: {}/{}", len(cleaned), len(raw_products))

    if not cleaned:
        logger.warning("清洗后无有效数据，跳过后续步骤")
        return result

    # ── Step 2: 保存 ────────────────────────────────────────────
    logger.info("保存数量…")
    saved_products: list[Product] = []

    for item in cleaned:
        try:
            product = Product(
                name=item.name,
                platform=item.platform,
                shop=item.shop,
                price=item.price,
                viewers=item.viewers,
                sales_24h=item.sales_24h,
                image=item.image,
            )
            session.add(product)
            saved_products.append(product)
        except Exception as e:
            logger.error("保存异常: {} → {}", item.name, e)

    try:
        await session.commit()
        for p in saved_products:
            await session.refresh(p)
    except Exception as e:
        logger.error("提交失败: {}", e)
        await session.rollback()
        result["saved_count"] = 0
        return result

    result["saved_count"] = len(saved_products)
    logger.info("保存数量: {}", len(saved_products))

    # ── Step 3: 创建历史快照 ─────────────────────────────────────
    now = datetime.now()
    history_records: list[ProductHistory] = []

    for product in saved_products:
        try:
            history = ProductHistory(
                product_id=product.id,
                price=product.price,
                sales_24h=product.sales_24h,
                viewers=product.viewers,
                ai_score=product.ai_score,
                record_time=now,
            )
            session.add(history)
            history_records.append(history)
        except Exception as e:
            logger.error("创建历史快照异常: product_id={} → {}", product.id, e)

    try:
        await session.commit()
    except Exception as e:
        logger.error("历史快照提交失败: {}", e)
        await session.rollback()

    result["history_count"] = len(history_records)
    logger.info("历史快照: {} 条", len(history_records))

    # ── Step 4: 趋势分析 ────────────────────────────────────────
    logger.info("分析完成…")
    from app.services.analytics.analyzer import TrendAnalyzer

    # 为每个商品查询历史并计算趋势
    trend_count = 0
    for product in saved_products:
        try:
            # 查询该商品的所有历史记录
            from sqlalchemy import select

            stmt = (
                select(ProductHistory)
                .where(ProductHistory.product_id == product.id)
                .order_by(ProductHistory.record_time)
            )
            query_result = await session.execute(stmt)
            histories = list(query_result.scalars().all())

            if len(histories) >= 2:
                analyzer = TrendAnalyzer(histories)
                trend_result = analyzer.calculate_trend_score()
                logger.debug(
                    "趋势分析: {} → score={}", product.name, trend_result["trend_score"]
                )
                trend_count += 1
        except Exception as e:
            logger.error("趋势分析异常: product_id={} → {}", product.id, e)

    result["trend_count"] = trend_count
    logger.info("分析完成: {} 个商品已分析", trend_count)

    # ── Step 5: 排行榜更新 ──────────────────────────────────────
    # 排行榜由 API 层实时计算（RankingService），无需额外缓存
    logger.info("排行榜更新完成")

    return result
