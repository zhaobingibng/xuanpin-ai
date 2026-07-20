"""Recommendation repository — persist and query daily recommendations."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.report_repository import ReportRepository
from app.models.daily_report import DailyReport


class RecommendationRepository:
    """推荐数据存储与查询。

    复用 DailyReport 基础设施，提供推荐专用的持久化和查询接口。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._report_repo = ReportRepository(session)

    # ── Save ──────────────────────────────────────────────────

    async def save_daily_recommendations(
        self, items: list[dict[str, Any]]
    ) -> DailyReport | None:
        """保存今日推荐到日报。

        同一天重复调用时覆盖旧记录。

        Args:
            items: 排序后的推荐商品列表。

        Returns:
            对应的 DailyReport 实例。
        """
        from sqlalchemy import delete

        from app.models.daily_report import DailyReportItem

        today = date.today()
        existing = await self._report_repo.find_by_date(today)

        hot = sum(1 for e in items if e.get("action") == "SELL")
        potential = sum(1 for e in items if e.get("action") == "TEST")
        avg = (
            round(sum(e["score"] for e in items) / len(items), 1)
            if items
            else 0.0
        )

        if existing is not None:
            existing.total = len(items)
            existing.hot_products = hot
            existing.potential_products = potential
            existing.average_score = avg
            await self._session.flush()

            await self._session.execute(
                delete(DailyReportItem).where(
                    DailyReportItem.report_id == existing.id
                )
            )
            await self._session.flush()

            await self._report_repo.save_items(existing.id, items)
            await self._session.commit()
            return existing

        db_report = DailyReport(
            report_date=today,
            total=len(items),
            hot_products=hot,
            potential_products=potential,
            average_score=avg,
        )
        await self._report_repo.create_report(db_report)
        await self._report_repo.save_items(db_report.id, items)
        await self._session.commit()
        return db_report

    # ── Queries ───────────────────────────────────────────────

    async def get_latest(self) -> DailyReport | None:
        """获取最新一期推荐（日报）。"""
        return await self._report_repo.get_latest()

    async def get_history(self, limit: int = 30) -> list[DailyReport]:
        """获取历史推荐（日报）列表。"""
        return list(await self._report_repo.get_history(limit=limit))
