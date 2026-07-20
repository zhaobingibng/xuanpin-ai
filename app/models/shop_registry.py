"""ShopRegistry ORM model — shop monitoring registry for Taobao and other platforms."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ShopRegistry(Base):
    """店铺注册表 — 管理需要监控的店铺信息。"""

    __tablename__ = "shop_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="平台名称 (taobao/tmall/jd/pdd)"
    )
    shop_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True, unique=True, comment="平台店铺唯一标识"
    )
    shop_name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="店铺名称"
    )
    shop_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="店铺首页链接"
    )
    category: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True, comment="主营品类"
    )
    fans: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="粉丝数"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="优先级 (1=低 2=中 3=高)"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True, comment="是否启用监控"
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近一次扫描时间"
    )
    monitor_strategy: Mapped[str] = mapped_column(
        String(50), nullable=False, default="daily", comment="监控策略 (daily/hourly/manual)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<ShopRegistry(id={self.id}, platform='{self.platform}', "
            f"shop_name='{self.shop_name}', enabled={self.enabled})>"
        )
