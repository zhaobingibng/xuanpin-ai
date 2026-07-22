"""RecommendationPoolInitializer — 推荐结果自动同步到推荐池 (Phase 46.3).

职责：
- 输入 report_date，查询当日 DailyReportItem
- 为每个推荐商品创建 recommendation_status(NEW)（若不存在）
- 不修改评分逻辑、不修改日报生成逻辑
- 幂等执行（重复调用不重复创建）

调用链：
    recommendation_task() → DailyRecommendationService.generate()
        → pool_initializer.sync(report_date)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.recommendation_status_repository import (
    RecommendationStatusRepository,
)
from app.models.daily_report import DailyReportItem


class RecommendationPoolInitializer:
    """推荐池初始化器 — 将 DailyReportItem 同步到 RecommendationStatus。

    Usage::

        async with session_factory() as session:
            initializer = RecommendationPoolInitializer(session)
            result = await initializer.sync(date.today())
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._status_repo = RecommendationStatusRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def sync(self, report_date: date) -> dict[str, Any]:
        """同步日报推荐结果到推荐池审核状态。

        流程：
        1. 查询 daily_report_items 中该日期的所有 product_id
        2. 对缺失 recommendation_status 的商品批量创建 NEW 记录
        3. 已存在 → 跳过

        Args:
            report_date: 推荐日期。

        Returns:
            {"synced": N, "skipped": N, "total": N, "report_date": str}
        """
        # 1. 查询当日推荐商品 ID 列表（通过 DailyReport.report_date JOIN）
        from app.models.daily_report import DailyReport

        stmt = (
            select(DailyReportItem.product_id)
            .join(DailyReport, DailyReport.id == DailyReportItem.report_id)
            .where(DailyReport.report_date == report_date)
            .distinct()
        )
        result = await self._session.execute(stmt)
        product_ids = [row[0] for row in result]

        total = len(product_ids)

        if total == 0:
            logger.info(
                "[PoolInit] report_date={} 无推荐商品，跳过同步", report_date
            )
            return {
                "synced": 0,
                "skipped": 0,
                "total": 0,
                "report_date": report_date.isoformat(),
            }

        # 2. 批量创建缺失的 NEW 状态记录
        created = await self._status_repo.ensure_status_records(
            product_ids, report_date
        )
        skipped = total - created

        logger.info(
            "[PoolInit] report_date={}: total={}, synced={}, skipped={}",
            report_date, total, created, skipped,
        )
        return {
            "synced": created,
            "skipped": skipped,
            "total": total,
            "report_date": report_date.isoformat(),
        }
