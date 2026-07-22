"""RecommendationPoolService — 推荐池查询 + 审核状态管理 (Phase 46.2).

不执行评分/匹配/排序逻辑（全量复用已有表数据）。
推荐池列表/详情 → 聚合查询（纯只读）。
审核状态 → recommendation_status 表写入。

约束：
- 全链路使用 PoolStatus 枚举，无裸字符串
- report_date 默认取最新 DailyReport.report_date
- Service 不返回 ORM 实体，统一返回 dict
- 状态流转校验在 Service（不在 Repository）
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.recommendation_pool_repository import (
    RecommendationPoolRepository,
)
from app.database.recommendation_status_repository import (
    RecommendationStatusRepository,
)
from app.models.recommendation_status import PoolStatus
from app.core.exceptions import RecommendationException


# ── 状态流转规则 ───────────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[PoolStatus, set[PoolStatus]] = {
    PoolStatus.NEW:       {PoolStatus.REVIEWED, PoolStatus.APPROVED, PoolStatus.REJECTED},
    PoolStatus.REVIEWED:  {PoolStatus.APPROVED, PoolStatus.REJECTED, PoolStatus.NEW},
    PoolStatus.APPROVED:  {PoolStatus.REJECTED, PoolStatus.REVIEWED, PoolStatus.PUBLISHED},
    PoolStatus.REJECTED:  {PoolStatus.NEW},
    PoolStatus.PUBLISHED: set(),  # 不可逆
}


class RecommendationPoolService:
    """推荐池服务。

    Usage::

        svc = RecommendationPoolService(session)
        pool = await svc.list_pool(status="NEW", limit=20)
        detail = await svc.get_pool_detail(product_id=42)
        await svc.update_status(product_id=42, status=PoolStatus.APPROVED, notes="可跟卖")
    """

    def __init__(self, session: AsyncSession) -> None:
        self._pool_repo = RecommendationPoolRepository(session)
        self._status_repo = RecommendationStatusRepository(session)

    # ── Query ──────────────────────────────────────────────────

    async def list_pool(
        self,
        report_date: date | None = None,
        status: PoolStatus | None = None,
        min_score: float | None = None,
        platform: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """查询推荐池列表。

        Args:
            report_date: 推荐日期（None = 最新）。
            status: 按审核状态筛选（None = 全部）。
            min_score: 最低评分。
            platform: 平台筛选。
            limit/offset: 分页。

        Returns:
            {"report_date": "2026-07-22", "total": N, "items": [...]}
        """
        effective_date = report_date
        if effective_date is None:
            effective_date = await self._pool_repo.get_latest_report_date()

        items = await self._pool_repo.list_pool(
            report_date=effective_date,
            status=status.value if status else None,
            min_score=min_score,
            platform=platform,
            limit=limit,
            offset=offset,
        )
        return {
            "report_date": effective_date.isoformat() if effective_date else None,
            "total": len(items),
            "items": items,
        }

    async def get_pool_detail(
        self, product_id: int, report_date: date | None = None
    ) -> dict | None:
        """获取单个推荐池条目详情（含全部 supplier_matches）。"""
        return await self._pool_repo.get_pool_detail(
            product_id=product_id, report_date=report_date
        )

    async def stats(self, report_date: date | None = None) -> dict:
        """推荐池统计。

        Returns:
            {"report_date": ..., "status_counts": {"NEW": n, ...}}
        """
        effective_date = report_date
        if effective_date is None:
            effective_date = await self._pool_repo.get_latest_report_date()

        counts = await self._status_repo.count_by_status(
            effective_date
        ) if effective_date else {s.value: 0 for s in PoolStatus}

        return {
            "report_date": effective_date.isoformat() if effective_date else None,
            "status_counts": counts,
        }

    # ── Status management ──────────────────────────────────────

    async def update_status(
        self,
        product_id: int,
        status: PoolStatus,
        notes: str | None = None,
        report_date: date | None = None,
    ) -> dict:
        """更新审核状态。

        业务规则：
        1. report_date 为空 → 自动取最新 DailyReport.report_date
        2. 状态流转校验（NEW→REVIEWED/APPROVED/REJECTED 等）
        3. 首次从 NEW 变为非 NEW → 自动记录 reviewed_at

        Args:
            product_id: 商品 ID。
            status: 目标状态（PoolStatus 枚举，不接收字符串）。
            notes: 审核备注。
            report_date: 推荐日期（None = 最新一期）。

        Returns:
            {"success": True, "product_id": int, "status": str, "reviewed_at": str|None, "report_date": str}

        Raises:
            ValueError: 状态流转非法 / 无推荐数据。
        """
        # 解析日期
        effective_date = report_date
        if effective_date is None:
            effective_date = await self._pool_repo.get_latest_report_date()
        if effective_date is None:
            raise RecommendationException(
                code="NO_RECOMMENDATION_DATA",
                message="暂无推荐数据，无法更新审核状态",
            )

        # 获取当前状态并校验流转
        current = await self._status_repo.get_status(product_id, effective_date)
        old_status = PoolStatus(current.status) if current else PoolStatus.NEW

        if old_status != status:
            self._validate_transition(old_status, status)

        # 写入
        record = await self._status_repo.upsert_status(
            product_id=product_id,
            report_date=effective_date,
            status=status,
            notes=notes,
        )

        return {
            "success": True,
            "product_id": product_id,
            "status": record.status,
            "previous_status": old_status.value,
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
            "report_date": effective_date.isoformat(),
        }

    # ── Internal ───────────────────────────────────────────────

    @staticmethod
    def _validate_transition(old: PoolStatus, new: PoolStatus) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(old, set())
        if new not in allowed:
            raise RecommendationException(
                code="INVALID_TRANSITION",
                message=f"不允许从 {old.value} 流转到 {new.value}。"
                f"允许的目标: {[s.value for s in allowed]}",
            )
