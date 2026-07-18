"""Logging configuration using loguru."""

import sys
from pathlib import Path

from loguru import logger

from app.config.settings import get_settings, BASE_DIR


def setup_logging() -> None:
    """Configure application-wide logging."""
    settings = get_settings()

    log_dir: Path = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console output
    logger.add(
        sys.stderr,
        level=settings.app_log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File output - general log
    logger.add(
        str(log_dir / "app.log"),
        level=settings.app_log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    # File output - error log
    logger.add(
        str(log_dir / "error.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    logger.info("Logging initialized | level={}", settings.app_log_level)
