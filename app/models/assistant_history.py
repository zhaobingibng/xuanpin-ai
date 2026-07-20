"""AssistantHistory ORM model — Q&A history for AI assistant."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AssistantHistory(Base):
    """AI助手问答历史记录。"""

    __tablename__ = "assistant_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="用户问题"
    )
    answer: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI回答（JSON字符串）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return f"<AssistantHistory(id={self.id}, question='{self.question[:30]}...')>"
