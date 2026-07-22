"""LoginSession ORM model — track platform login state."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LoginStatus(str, Enum):
    """Login status enumeration."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class LoginSession(Base):
    """Platform login session tracking.

    Stores the last known login state for each platform,
    enabling pre-crawl validation and expiry detection.
    """

    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True, comment="平台名称 (taobao/1688/etc)"
    )
    username: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="登录用户名"
    )
    login_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近登录时间"
    )
    last_check_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近检测时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LoginStatus.UNKNOWN.value,
        comment="登录状态: ACTIVE/EXPIRED/UNKNOWN",
    )

    @property
    def is_active(self) -> bool:
        """Check if session is actively logged in."""
        return self.status == LoginStatus.ACTIVE.value

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return self.status == LoginStatus.EXPIRED.value

    def mark_active(self, username: str | None = None) -> None:
        """Mark session as active."""
        self.status = LoginStatus.ACTIVE.value
        self.last_check_time = func.now()
        if username:
            self.username = username

    def mark_expired(self) -> None:
        """Mark session as expired."""
        self.status = LoginStatus.EXPIRED.value
        self.last_check_time = func.now()

    def mark_unknown(self) -> None:
        """Mark session status as unknown."""
        self.status = LoginStatus.UNKNOWN.value
        self.last_check_time = func.now()

    def __repr__(self) -> str:
        return (
            f"<LoginSession(id={self.id}, platform='{self.platform}', "
            f"username='{self.username}', status='{self.status}')>"
        )
