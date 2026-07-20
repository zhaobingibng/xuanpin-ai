"""CrawlLog ORM model — track individual crawl task history."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CrawlLog(Base):
    """采集日志记录。"""

    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True, comment="搜索关键词"
    )
    platform: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="平台名称"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="开始时间"
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="结束时间"
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="采集总数")
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="成功数")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败数")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RUNNING", comment="状态: RUNNING/SUCCESS/FAILED"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlLog(id={self.id}, keyword='{self.keyword}', "
            f"platform='{self.platform}', status='{self.status}')>"
        )
