"""DailyTaskLog ORM model — 每日选品任务执行日志."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DailyTaskLog(Base):
    """每日选品任务执行日志。

    记录每次任务执行的状态和结果。
    """

    __tablename__ = "daily_task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="任务名称")
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="开始时间")
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING", comment="状态: RUNNING/SUCCESS/FAILED")

    # 统计
    products_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="采集商品数")
    new_products_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="新品数量")
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="匹配成功数")

    # 日报
    report_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="日报是否发送")

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True, comment="错误信息")

    def __repr__(self) -> str:
        return (
            f"<DailyTaskLog(id={self.id}, task='{self.task_name}', "
            f"status='{self.status}', products={self.products_count})>"
        )
