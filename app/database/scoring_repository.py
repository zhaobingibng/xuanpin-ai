"""Scoring config repository — manage dynamic scoring weight configurations."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scoring_config import DEFAULT_WEIGHTS, ScoringConfig


class ScoringRepository:
    """评分配置数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Query ─────────────────────────────────────────────────

    async def get_active(self) -> ScoringConfig | None:
        """获取当前生效的评分配置。"""
        stmt = (
            select(ScoringConfig)
            .where(ScoringConfig.is_active.is_(True))
            .order_by(ScoringConfig.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, limit: int = 10) -> Sequence[ScoringConfig]:
        """获取历史配置版本。"""
        stmt = (
            select(ScoringConfig)
            .order_by(ScoringConfig.version.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ── Save ──────────────────────────────────────────────────

    async def save(self, config: ScoringConfig) -> ScoringConfig:
        """保存新的评分配置。"""
        self._session.add(config)
        await self._session.flush()
        return config

    # ── Update weights ────────────────────────────────────────

    async def update_weights(self, weights: dict[str, float]) -> ScoringConfig:
        """基于当前活跃配置生成新版本。

        旧版本标记为 inactive，新版本标记为 active。

        Args:
            weights: {"sales_weight": float, "trend_weight": float, ...}

        Returns:
            新创建的 ScoringConfig 实例。
        """
        current = await self.get_active()
        new_version = (current.version + 1) if current else 1

        if current is not None:
            current.is_active = False
            await self._session.flush()

        base_name = current.name if current else "default"
        new_config = ScoringConfig(
            name=base_name,
            sales_weight=weights.get("sales_weight", DEFAULT_WEIGHTS["sales_weight"]),
            trend_weight=weights.get("trend_weight", DEFAULT_WEIGHTS["trend_weight"]),
            viewer_weight=weights.get("viewer_weight", DEFAULT_WEIGHTS["viewer_weight"]),
            price_weight=weights.get("price_weight", DEFAULT_WEIGHTS["price_weight"]),
            competition_weight=weights.get("competition_weight", DEFAULT_WEIGHTS["competition_weight"]),
            version=new_version,
            is_active=True,
        )
        return await self.save(new_config)
