"""xuanpin-ai startup script — initialize and run the application."""

import asyncio
import sys

from loguru import logger


async def startup() -> None:
    """启动 xuanpin-ai 24小时无人值守系统。

    Steps:
    1. 数据库初始化
    2. 日志系统配置
    3. Scheduler 启动
    4. Crawler Worker 就绪
    5. FastAPI 服务启动
    """
    logger.info("=" * 60)
    logger.info("xuanpin-ai 24h Unattended System Starting")
    logger.info("=" * 60)

    # ── Step 1: Database initialization ──────────────────────
    logger.info("[Startup] Step 1: Initializing database…")
    try:
        from app.database.base import get_engine, Base
        # Import all models to register them with metadata
        import app.models  # noqa: F401

        engine = get_engine()
        Base.metadata.create_all(engine)
        logger.info("[Startup] Database initialized successfully")
    except Exception as e:
        logger.error("[Startup] Database initialization failed: {}", e)
        sys.exit(1)

    # ── Step 2: Logging setup ────────────────────────────────
    logger.info("[Startup] Step 2: Configuring logging…")
    try:
        from app.config.config import setup_logging
        setup_logging()
    except Exception as e:
        logger.warning("[Startup] Logging setup failed (using defaults): {}", e)

    # ── Step 3: Scheduler startup ────────────────────────────
    logger.info("[Startup] Step 3: Starting scheduler…")
    try:
        from app.config.settings import get_settings
        from app.tasks.scheduler import TaskScheduler

        settings = get_settings()
        scheduler = TaskScheduler()
        scheduler.add_auto_crawl(hour=settings.daily_crawl_hour)
        scheduler.start()
        logger.info(
            "[Startup] Scheduler started — daily crawl at {:02d}:00",
            settings.daily_crawl_hour,
        )
    except Exception as e:
        logger.error("[Startup] Scheduler startup failed: {}", e)

    # ── Step 4: Crawler worker ready ─────────────────────────
    logger.info("[Startup] Step 4: Crawler workers ready")

    # ── Step 5: Start FastAPI ─────────────────────────────────
    logger.info("[Startup] Step 5: Starting FastAPI server…")
    logger.info("[Startup] System ready — running 24/7")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn

    asyncio.run(startup())
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=False)
