"""Logging system setup — RotatingFileHandler with daily rotation."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: str = "logs", retention_days: int = 30) -> None:
    """配置日志系统：控制台 + 文件轮转。

    日志文件：
    - logs/app.log       — 全部日志
    - logs/crawler.log   — 采集相关
    - logs/error.log     — 错误级别

    每天自动切割，保留 retention_days 天。
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console output
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - {message}",
    )

    # app.log — all levels, daily rotation
    logger.add(
        str(log_path / "app.log"),
        rotation="00:00",
        retention=f"{retention_days} days",
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )

    # crawler.log — crawler-specific logs
    logger.add(
        str(log_path / "crawler.log"),
        rotation="00:00",
        retention=f"{retention_days} days",
        level="DEBUG",
        encoding="utf-8",
        filter=lambda record: "crawler" in record["name"].lower(),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )

    # error.log — errors only
    logger.add(
        str(log_path / "error.log"),
        rotation="00:00",
        retention=f"{retention_days} days",
        level="ERROR",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )

    logger.info("Logging configured: {} (retention={}d)", log_path, retention_days)
