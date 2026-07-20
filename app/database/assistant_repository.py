"""Assistant repository — persist and query Q&A history."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant_history import AssistantHistory


class AssistantRepository:
    """AI助手问答历史数据存取。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, question: str, answer: str) -> AssistantHistory:
        """保存一条问答记录。"""
        record = AssistantHistory(question=question, answer=answer)
        self._session.add(record)
        await self._session.flush()
        return record

    async def history(self, limit: int = 30) -> Sequence[AssistantHistory]:
        """获取最近的问答历史（按时间降序）。"""
        stmt = (
            select(AssistantHistory)
            .order_by(AssistantHistory.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
