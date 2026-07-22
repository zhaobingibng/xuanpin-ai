"""RecommendationStatusRepository — 推荐池审核状态持久化 (Phase 46.2).

仅操作 recommendation_status 表。状态流转校验放在 Service 层。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation_status import PoolStatus, RecommendationStatus


class RecommendationStatusRepository:
    """审核状态 CRUD（纯数据访问，无业务规则）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Upsert ─────────────────────────────────────────────────

    async def upsert_status(
        self,
        product_id: int,
        report_date: date,
        status: PoolStatus,
        notes: str | None = None,
    ) -> RecommendationStatus:
        """插入或更新审核状态。

        - 首次创建 → 所有字段由调用方指定
        - 已存在且 status 不同 → 更新 status + notes + reviewed_at（若首次非 NEW）
        - 已存在且 status 相同 → 仅更新 notes（幂等）

        Args:
            product_id: 商品 ID。
            report_date: 推荐日期。
            status: PoolStatus 枚举值。
            notes: 可选的审核备注。

        Returns:
            当前生效的 RecommendationStatus ORM 记录。
        """
        stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id == product_id,
            RecommendationStatus.report_date == report_date,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            old_status = PoolStatus(existing.status)
            existing.status = status.value
            existing.review_notes = notes if notes is not None else existing.review_notes
            # 首次从 NEW 变为非 NEW 时记录时间
            if old_status == PoolStatus.NEW and status != PoolStatus.NEW:
                existing.reviewed_at = datetime.now()
            await self._session.flush()
            return existing

        record = RecommendationStatus(
            product_id=product_id,
            report_date=report_date,
            status=status.value,
            review_notes=notes,
            reviewed_at=datetime.now() if status != PoolStatus.NEW else None,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    # ── Query ──────────────────────────────────────────────────

    async def get_status(
        self, product_id: int, report_date: date
    ) -> RecommendationStatus | None:
        """获取指定商品在某天的审核状态。"""
        stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id == product_id,
            RecommendationStatus.report_date == report_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def batch_get_statuses(
        self, product_ids: list[int], report_date: date
    ) -> dict[int, RecommendationStatus]:
        """批量查询审核状态 → {product_id: RecommendationStatus}。

        用于推荐池列表聚合时一次性查所有状态，避免 N+1。
        """
        if not product_ids:
            return {}
        stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id.in_(product_ids),
            RecommendationStatus.report_date == report_date,
        )
        result = await self._session.execute(stmt)
        return {r.product_id: r for r in result.scalars().all()}

    async def ensure_status_records(
        self, product_ids: list[int], report_date: date
    ) -> int:
        """批量初始化缺失的审核状态记录。

        对每个 product_id，若 recommendation_status 不存在 → 创建 NEW 记录。
        已存在 → 跳过（幂等）。

        Args:
            product_ids: 待初始化的商品 ID 列表。
            report_date: 推荐日期。

        Returns:
            新创建的记录数。
        """
        if not product_ids:
            return 0

        # 查询已有 product_ids
        stmt = select(RecommendationStatus.product_id).where(
            RecommendationStatus.product_id.in_(product_ids),
            RecommendationStatus.report_date == report_date,
        )
        result = await self._session.execute(stmt)
        existing_ids: set[int] = {row[0] for row in result}

        missing = [pid for pid in set(product_ids) if pid not in existing_ids]
        if not missing:
            return 0

        now = datetime.now()
        for pid in missing:
            self._session.add(
                RecommendationStatus(
                    product_id=pid,
                    report_date=report_date,
                    status=PoolStatus.NEW.value,
                )
            )
        await self._session.flush()
        return len(missing)

    async def count_by_status(self, report_date: date) -> dict[str, int]:
        """按状态统计数量 → {"NEW": n, "REVIEWED": n, "APPROVED": n, "REJECTED": n}。"""
        from sqlalchemy import func as sa_func

        stmt = (
            select(
                RecommendationStatus.status,
                sa_func.count(RecommendationStatus.id),
            )
            .where(RecommendationStatus.report_date == report_date)
            .group_by(RecommendationStatus.status)
        )
        result = await self._session.execute(stmt)
        counts: dict[str, int] = {
            PoolStatus.NEW.value: 0,
            PoolStatus.REVIEWED.value: 0,
            PoolStatus.APPROVED.value: 0,
            PoolStatus.REJECTED.value: 0,
        }
        for row in result:
            counts[row[0]] = row[1]
        return counts
