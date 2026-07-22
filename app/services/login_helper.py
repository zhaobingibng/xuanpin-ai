"""Login helper service — Interactive login and state persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_session import LoginSession, LoginStatus


# ── State File Paths ───────────────────────────────────────────

# Use project root directory for consistent paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
TAOBAO_STATE_PATH = PROJECT_ROOT / "storage" / "taobao_state.json"
ALIBABA_STATE_PATH = PROJECT_ROOT / "storage" / "alibaba_state.json"


class LoginHelper:
    """登录辅助服务。

    功能：
    - 保存登录状态到文件
    - 读取登录状态文件
    - 更新数据库中的登录会话记录

    使用示例：
        helper = LoginHelper(session)
        await helper.save_login_state("taobao", state_data)
        await helper.update_login_session("taobao", "user123", LoginStatus.ACTIVE)
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """Initialize login helper.

        Args:
            session: Optional database session for LoginSession operations.
        """
        self._session = session

    # ── State File Operations ──────────────────────────────────

    def get_state_path(self, platform: str) -> Path:
        """Get state file path for platform.

        Args:
            platform: Platform name (taobao, 1688).

        Returns:
            Path to state file.
        """
        if platform == "taobao":
            return TAOBAO_STATE_PATH
        elif platform in ("1688", "alibaba"):
            return ALIBABA_STATE_PATH
        else:
            return Path(f"storage/{platform}_state.json")

    def save_state_file(self, platform: str, state_data: dict[str, Any]) -> bool:
        """Save login state to file.

        Args:
            platform: Platform name.
            state_data: State data to save (cookies, localStorage, etc.).

        Returns:
            True if saved successfully.
        """
        path = self.get_state_path(platform)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[LoginHelper] State saved: {path}")
            return True
        except Exception as e:
            logger.error(f"[LoginHelper] Failed to save state: {e}")
            return False

    def load_state_file(self, platform: str) -> dict[str, Any] | None:
        """Load login state from file.

        Args:
            platform: Platform name.

        Returns:
            State data dict, or None if not found.
        """
        path = self.get_state_path(platform)

        if not path.exists():
            logger.info(f"[LoginHelper] State file not found: {path}")
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"[LoginHelper] State loaded: {path}")
            return data
        except Exception as e:
            logger.error(f"[LoginHelper] Failed to load state: {e}")
            return None

    def has_state_file(self, platform: str) -> bool:
        """Check if state file exists.

        Args:
            platform: Platform name.

        Returns:
            True if state file exists.
        """
        path = self.get_state_path(platform)
        return path.exists() and path.stat().st_size > 0

    # ── LoginSession Database Operations ───────────────────────

    async def update_login_session(
        self,
        platform: str,
        username: str | None = None,
        status: LoginStatus = LoginStatus.ACTIVE,
    ) -> bool:
        """Update login session in database.

        Args:
            platform: Platform name.
            username: Optional username.
            status: Login status.

        Returns:
            True if updated successfully.
        """
        if self._session is None:
            logger.warning("[LoginHelper] No database session provided")
            return False

        try:
            # Find existing session
            query = select(LoginSession).where(LoginSession.platform == platform)
            result = await self._session.execute(query)
            session = result.scalar_one_or_none()

            now = datetime.now()

            if session is None:
                # Create new session
                session = LoginSession(
                    platform=platform,
                    username=username,
                    status=status.value,
                    login_time=now,
                    last_check_time=now,
                )
                self._session.add(session)
                logger.info(f"[LoginHelper] Created login session: {platform} ({status.value})")
            else:
                # Update existing session
                session.status = status.value
                session.last_check_time = now
                if username:
                    session.username = username
                if status == LoginStatus.ACTIVE:
                    session.login_time = now
                logger.info(f"[LoginHelper] Updated login session: {platform} ({status.value})")

            await self._session.flush()
            return True

        except Exception as e:
            logger.error(f"[LoginHelper] Failed to update login session: {e}")
            return False

    async def get_login_session(self, platform: str) -> LoginSession | None:
        """Get login session from database.

        Args:
            platform: Platform name.

        Returns:
            LoginSession or None.
        """
        if self._session is None:
            return None

        try:
            query = select(LoginSession).where(LoginSession.platform == platform)
            result = await self._session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[LoginHelper] Failed to get login session: {e}")
            return None

    async def mark_login_success(
        self,
        platform: str,
        state_data: dict[str, Any],
        username: str | None = None,
    ) -> bool:
        """Mark login as successful - save state and update session.

        Args:
            platform: Platform name.
            state_data: Login state data.
            username: Optional username.

        Returns:
            True if successful.
        """
        # Save state file
        if not self.save_state_file(platform, state_data):
            return False

        # Update database session
        if not await self.update_login_session(platform, username, LoginStatus.ACTIVE):
            logger.warning(f"[LoginHelper] State saved but session update failed for {platform}")

        return True

    async def mark_login_expired(self, platform: str) -> bool:
        """Mark login as expired.

        Args:
            platform: Platform name.

        Returns:
            True if updated successfully.
        """
        return await self.update_login_session(platform, status=LoginStatus.EXPIRED)

    # ── Status Summary ─────────────────────────────────────────

    async def get_login_status_summary(self) -> dict[str, dict[str, Any]]:
        """Get login status summary for all platforms.

        Returns:
            Dict with platform status info.
        """
        summary = {}

        for platform in ["taobao", "1688"]:
            state_exists = self.has_state_file(platform)
            session = await self.get_login_session(platform) if self._session else None

            summary[platform] = {
                "state_file_exists": state_exists,
                "state_file_path": str(self.get_state_path(platform)),
                "db_session_exists": session is not None,
                "db_status": session.status if session else None,
                "username": session.username if session else None,
                "is_active": session.is_active if session else False,
            }

        return summary


# ── CLI Entry Point ────────────────────────────────────────────


async def main() -> int:
    """Main entry point for manual login state management."""
    from app.database.base import get_async_session_factory

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        helper = LoginHelper(session)

        # Show current status
        print("\n" + "=" * 50)
        print("Login Status Summary")
        print("=" * 50)

        summary = await helper.get_login_status_summary()

        for platform, info in summary.items():
            print(f"\n[{platform}]")
            print(f"  State file: {info['state_file_path']}")
            print(f"  State exists: {info['state_file_exists']}")
            print(f"  DB status: {info['db_status'] or 'NOT_FOUND'}")
            print(f"  Username: {info['username'] or 'N/A'}")
            print(f"  Is active: {info['is_active']}")

        print("\n" + "=" * 50)

    return 0


if __name__ == "__main__":
    import asyncio
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
