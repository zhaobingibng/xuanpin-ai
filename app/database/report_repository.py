"""Report repository — CRUD for DailyReport and DailyReportItem."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.daily_report import DailyReport, DailyReportItem


class ReportRepository:
    """Async repository for DailyReport persistence.

    Dedup rule:
      Same report_date → update existing report (no duplicate).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────

    async def create_report(self, report: DailyReport) -> DailyReport:
        """Insert a new daily report record and return it."""
        self._session.add(report)
        await self._session.flush()
        return report

    # ── Save items ────────────────────────────────────────────

    async def save_items(
        self, report_id: int, items: list[dict[str, Any]]
    ) -> list[DailyReportItem]:
        """Batch-insert report items from scored dicts.

        Each item dict should contain:
          rank, product_id, name, platform, image, price, score, level, reasons

        Returns:
            List of created DailyReportItem instances.
        """
        created: list[DailyReportItem] = []
        for entry in items:
            reasons = entry.get("reasons", [])
            reasons_json = json.dumps(reasons, ensure_ascii=False) if isinstance(reasons, list) else str(reasons)
            item = DailyReportItem(
                report_id=report_id,
                product_id=entry["product_id"],
                rank=entry["rank"],
                name=entry["name"],
                platform=entry["platform"],
                image=entry.get("image", ""),
                price=entry["price"],
                score=entry["score"],
                level=entry["level"],
                reasons=reasons_json,
            )
            self._session.add(item)
            created.append(item)
        await self._session.flush()
        return created

    # ── Query ─────────────────────────────────────────────────

    async def get_latest(self) -> DailyReport | None:
        """Fetch the most recent daily report with items."""
        stmt = (
            select(DailyReport)
            .options(selectinload(DailyReport.items))
            .order_by(DailyReport.report_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, limit: int = 30) -> Sequence[DailyReport]:
        """Fetch recent daily reports (summary only, no items eager-loaded)."""
        stmt = (
            select(DailyReport)
            .order_by(DailyReport.report_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_report_detail(self, report_id: int) -> DailyReport | None:
        """Fetch a single daily report with all its items."""
        stmt = (
            select(DailyReport)
            .options(selectinload(DailyReport.items))
            .where(DailyReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Dedup: find by date ───────────────────────────────────

    async def find_by_date(self, report_date: date) -> DailyReport | None:
        """Find an existing report for the given date."""
        stmt = select(DailyReport).where(DailyReport.report_date == report_date)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
