"""RecommendationPublishRepository — 发布记录持久化 (Phase 46.4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation_publish_record import (
    PublishStatus,
    RecommendationPublishRecord,
)
from app.core.exceptions import PublishException


class RecommendationPublishRepository:
    """发布记录 CRUD（纯数据访问，无业务规则）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ─────────────────────────────────────────────────

    async def create_record(
        self,
        product_id: int,
        platform: str = "taobao",
    ) -> RecommendationPublishRecord:
        """创建一条 PENDING 发布记录。

        Args:
            product_id: 商品 ID。
            platform: 目标平台。

        Returns:
            新创建的发布记录。
        """
        record = RecommendationPublishRecord(
            product_id=product_id,
            status=PublishStatus.PENDING.value,
            platform=platform,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    # ── Update ─────────────────────────────────────────────────

    async def mark_success(self, record_id: int) -> RecommendationPublishRecord:
        """标记发布成功。"""
        record = await self._get_by_id(record_id)
        if record is None:
            raise PublishException(
                code="RECORD_NOT_FOUND",
                message=f"发布记录 {record_id} 不存在",
            )
        record.status = PublishStatus.SUCCESS.value
        record.published_at = datetime.now()
        await self._session.flush()
        return record

    async def mark_failed(
        self, record_id: int, error_message: str
    ) -> RecommendationPublishRecord:
        """标记发布失败。"""
        record = await self._get_by_id(record_id)
        if record is None:
            raise PublishException(
                code="RECORD_NOT_FOUND",
                message=f"发布记录 {record_id} 不存在",
            )
        record.status = PublishStatus.FAILED.value
        record.error_message = error_message
        record.retry_count += 1
        await self._session.flush()
        return record

    # ── Query ──────────────────────────────────────────────────

    async def get_history(
        self, product_id: int, limit: int = 20
    ) -> list[RecommendationPublishRecord]:
        """查询某商品的发布历史（最新的在前）。"""
        stmt = (
            select(RecommendationPublishRecord)
            .where(RecommendationPublishRecord.product_id == product_id)
            .order_by(desc(RecommendationPublishRecord.id))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self, product_id: int
    ) -> RecommendationPublishRecord | None:
        """查询最近一次发布记录。"""
        stmt = (
            select(RecommendationPublishRecord)
            .where(RecommendationPublishRecord.product_id == product_id)
            .order_by(desc(RecommendationPublishRecord.id))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Internal ───────────────────────────────────────────────

    async def _get_by_id(self, record_id: int) -> RecommendationPublishRecord | None:
        stmt = select(RecommendationPublishRecord).where(
            RecommendationPublishRecord.id == record_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
