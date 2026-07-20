"""FailedTask ORM model — track failed tasks for retry management."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


# ── Status Constants ────────────────────────────────────────────

STATUS_PENDING = "PENDING"
STATUS_RETRYING = "RETRYING"
STATUS_FAILED = "FAILED"
STATUS_RESOLVED = "RESOLVED"

VALID_STATUSES = frozenset({STATUS_PENDING, STATUS_RETRYING, STATUS_FAILED, STATUS_RESOLVED})


class FailedTask(Base):
    """失败任务记录。

    Tracks failed tasks with retry lifecycle management.
    """

    __tablename__ = "failed_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True, comment="任务名称"
    )
    payload: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="任务参数 (JSON)"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )
    exception_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="异常类型"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="重试次数"
    )
    max_retry: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, comment="最大重试次数"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PENDING, index=True, comment="状态"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<FailedTask(id={self.id}, task='{self.task_name}', "
            f"status='{self.status}', retry={self.retry_count}/{self.max_retry})>"
        )

    def can_retry(self) -> bool:
        """Check if this task can be retried."""
        return self.retry_count < self.max_retry and self.status in (STATUS_PENDING, STATUS_FAILED)
