"""System health check service — Production readiness validation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_session import LoginSession


class HealthCheckService:
    """系统健康检查服务。

    检查项：
    1. 数据库连接
    2. 淘宝登录状态
    3. 1688登录状态
    4. 飞书配置

    使用示例：
        service = HealthCheckService(session)
        report = await service.run_all_checks()
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            session: Async SQLAlchemy session.
        """
        self._session = session
        self._results: dict[str, dict[str, Any]] = {}

    @property
    def results(self) -> dict[str, dict[str, Any]]:
        """Return check results."""
        return self._results.copy()

    @property
    def is_healthy(self) -> bool:
        """Check if all critical checks passed."""
        critical_checks = ["database", "taobao_login", "alibaba_login"]
        for check in critical_checks:
            if check in self._results and not self._results[check].get("ok", False):
                return False
        return True

    async def check_database(self) -> dict[str, Any]:
        """Check database connection.

        Returns:
            Check result dict.
        """
        try:
            # Execute simple query to verify connection
            result = await self._session.execute(text("SELECT 1"))
            await result.scalar()

            self._results["database"] = {
                "ok": True,
                "message": "Database connection OK",
            }
            logger.info("[Health] Database: OK")
            return self._results["database"]

        except Exception as e:
            self._results["database"] = {
                "ok": False,
                "message": f"Database error: {e}",
            }
            logger.error(f"[Health] Database: FAILED - {e}")
            return self._results["database"]

    async def check_taobao_login(self) -> dict[str, Any]:
        """Check Taobao login status.

        Returns:
            Check result dict.
        """
        try:
            query = select(LoginSession).where(LoginSession.platform == "taobao")
            result = await self._session.execute(query)
            session = result.scalar_one_or_none()

            if session is None:
                self._results["taobao_login"] = {
                    "ok": False,
                    "message": "No Taobao login session found",
                    "status": "NOT_FOUND",
                }
            elif session.is_active:
                self._results["taobao_login"] = {
                    "ok": True,
                    "message": f"Taobao login active (user: {session.username or 'unknown'})",
                    "status": "ACTIVE",
                    "username": session.username,
                    "login_time": session.login_time.isoformat() if session.login_time else None,
                }
            else:
                self._results["taobao_login"] = {
                    "ok": False,
                    "message": f"Taobao login expired (status: {session.status})",
                    "status": session.status,
                }

            logger.info(f"[Health] Taobao login: {self._results['taobao_login']['status']}")
            return self._results["taobao_login"]

        except Exception as e:
            self._results["taobao_login"] = {
                "ok": False,
                "message": f"Check failed: {e}",
                "status": "ERROR",
            }
            logger.error(f"[Health] Taobao login: FAILED - {e}")
            return self._results["taobao_login"]

    async def check_alibaba_login(self) -> dict[str, Any]:
        """Check 1688 login status.

        Returns:
            Check result dict.
        """
        try:
            query = select(LoginSession).where(LoginSession.platform == "1688")
            result = await self._session.execute(query)
            session = result.scalar_one_or_none()

            if session is None:
                self._results["alibaba_login"] = {
                    "ok": False,
                    "message": "No 1688 login session found",
                    "status": "NOT_FOUND",
                }
            elif session.is_active:
                self._results["alibaba_login"] = {
                    "ok": True,
                    "message": f"1688 login active (user: {session.username or 'unknown'})",
                    "status": "ACTIVE",
                    "username": session.username,
                    "login_time": session.login_time.isoformat() if session.login_time else None,
                }
            else:
                self._results["alibaba_login"] = {
                    "ok": False,
                    "message": f"1688 login expired (status: {session.status})",
                    "status": session.status,
                }

            logger.info(f"[Health] 1688 login: {self._results['alibaba_login']['status']}")
            return self._results["alibaba_login"]

        except Exception as e:
            self._results["alibaba_login"] = {
                "ok": False,
                "message": f"Check failed: {e}",
                "status": "ERROR",
            }
            logger.error(f"[Health] 1688 login: FAILED - {e}")
            return self._results["alibaba_login"]

    def check_feishu_config(self, config_path: str | None = None) -> dict[str, Any]:
        """Check Feishu configuration.

        Args:
            config_path: Path to feishu.json config file.

        Returns:
            Check result dict.
        """
        if config_path is None:
            config_file = Path(__file__).parent.parent.parent / "config" / "feishu.json"
        else:
            config_file = Path(config_path)

        try:
            if not config_file.exists():
                self._results["feishu_config"] = {
                    "ok": False,
                    "message": f"Config file not found: {config_file}",
                    "enabled": False,
                }
            else:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                enabled = config.get("enabled", False)
                webhook_url = config.get("webhook_url", "")

                if enabled and webhook_url:
                    self._results["feishu_config"] = {
                        "ok": True,
                        "message": "Feishu notification enabled",
                        "enabled": True,
                        "webhook_configured": True,
                    }
                elif enabled and not webhook_url:
                    self._results["feishu_config"] = {
                        "ok": False,
                        "message": "Feishu enabled but webhook_url not configured",
                        "enabled": True,
                        "webhook_configured": False,
                    }
                else:
                    self._results["feishu_config"] = {
                        "ok": True,  # Not enabled is OK (optional feature)
                        "message": "Feishu notification disabled (optional)",
                        "enabled": False,
                    }

            logger.info(f"[Health] Feishu config: {self._results['feishu_config']['message']}")
            return self._results["feishu_config"]

        except Exception as e:
            self._results["feishu_config"] = {
                "ok": False,
                "message": f"Config error: {e}",
                "enabled": False,
            }
            logger.error(f"[Health] Feishu config: FAILED - {e}")
            return self._results["feishu_config"]

    async def run_all_checks(self) -> dict[str, Any]:
        """Run all health checks.

        Returns:
            Complete health report.
        """
        logger.info("[Health] Running system health checks...")

        # Run all checks
        await self.check_database()
        await self.check_taobao_login()
        await self.check_alibaba_login()
        self.check_feishu_config()

        # Generate report
        report = {
            "timestamp": datetime.now().isoformat(),
            "is_healthy": self.is_healthy,
            "checks": self._results,
            "summary": self._generate_summary(),
        }

        logger.info(f"[Health] System health: {'HEALTHY' if self.is_healthy else 'UNHEALTHY'}")
        return report

    def _generate_summary(self) -> str:
        """Generate human-readable summary.

        Returns:
            Summary string.
        """
        lines = ["=" * 50, "系统健康报告", "=" * 50, ""]

        # Database
        db = self._results.get("database", {})
        status = "OK" if db.get("ok") else "FAILED"
        lines.append(f"[{status}] 数据库连接: {db.get('message', 'Unknown')}")

        # Taobao
        tb = self._results.get("taobao_login", {})
        status = "OK" if tb.get("ok") else "FAILED"
        lines.append(f"[{status}] 淘宝登录: {tb.get('message', 'Unknown')}")

        # 1688
        ali = self._results.get("alibaba_login", {})
        status = "OK" if ali.get("ok") else "FAILED"
        lines.append(f"[{status}] 1688登录: {ali.get('message', 'Unknown')}")

        # Feishu
        fs = self._results.get("feishu_config", {})
        status = "OK" if fs.get("ok") else "WARN"
        lines.append(f"[{status}] 飞书配置: {fs.get('message', 'Unknown')}")

        lines.append("")
        lines.append("=" * 50)
        overall = "HEALTHY" if self.is_healthy else "UNHEALTHY"
        lines.append(f"总体状态: {overall}")
        lines.append("=" * 50)

        return "\n".join(lines)

    def format_report(self) -> str:
        """Format health report as string.

        Returns:
            Formatted report string.
        """
        return self._generate_summary()


async def run_startup_checks(session: AsyncSession) -> dict[str, Any]:
    """Run startup health checks.

    This is the main entry point for production readiness validation.

    Args:
        session: Database session.

    Returns:
        Health report dict.
    """
    service = HealthCheckService(session)
    return await service.run_all_checks()
