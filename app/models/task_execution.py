"""TaskExecution ORM model — track individual task execution history."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class TaskExecution(Base):
    """任务执行记录。"""

    __tablename__ = "task_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True, comment="任务名称"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="开始时间"
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="结束时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RUNNING", comment="状态: RUNNING/SUCCESS/FAILED"
    )
    duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="执行时长(秒)"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )

    def __repr__(self) -> str:
        return (
            f"<TaskExecution(id={self.id}, task='{self.task_name}', "
            f"status='{self.status}')>"
        )
