"""CrawlerStatus ORM model — track crawler execution status."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CrawlerStatus(Base):
    """采集运行状态记录。"""

    __tablename__ = "crawler_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="平台名称"
    )
    last_run_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="最近运行时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RUNNING", comment="运行状态: RUNNING/SUCCESS/FAILED"
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="采集总数")
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="成功数")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败数")
    message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="附加信息/错误描述"
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlerStatus(id={self.id}, platform='{self.platform}', "
            f"status='{self.status}')>"
        )
