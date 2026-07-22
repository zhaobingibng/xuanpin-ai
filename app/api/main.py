"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.assistant import router as assistant_router
from app.api.ai_analysis import router as ai_analysis_router
from app.api.crawler import router as crawler_router
from app.api.dashboard import router as dashboard_router
from app.api.knowledge import router as knowledge_router
from app.api.learning import router as learning_router
from app.api.products import router as products_router
from app.api.ranking import router as ranking_router
from app.api.recommendations import router as recommendations_router
from app.api.reports import router as reports_router
from app.api.reviews import router as reviews_router
from app.api.stats import router as stats_router
from app.api.strategy import router as strategy_router
from app.api.system import router as system_router
from app.api.metrics import router as metrics_router
from app.api.tasks import router as tasks_router
from app.api.selection import router as selection_router
from app.api.shops import router as shops_router

_scheduler_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: start/stop scheduler."""
    global _scheduler_instance
    try:
        from app.config.settings import get_settings
        from app.tasks.scheduler import TaskScheduler

        settings = get_settings()
        _scheduler_instance = TaskScheduler()
        _scheduler_instance.add_auto_crawl(hour=settings.daily_crawl_hour)

        if settings.daily_selection_enabled:
            _scheduler_instance.add_daily_selection()
            logger.info(
                "Scheduler auto-registered daily_selection (enabled via DAILY_SELECTION_ENABLED)",
            )

        _scheduler_instance.start()
        logger.info("Scheduler auto-registered daily_crawl at {:02d}:00", settings.daily_crawl_hour)
    except Exception as e:
        logger.warning("Scheduler startup failed: {}", e)
    yield
    if _scheduler_instance is not None:
        _scheduler_instance.stop()
        _scheduler_instance = None


app = FastAPI(title="xuanpin-ai API", lifespan=lifespan)

# ── CORS ────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assistant_router)
app.include_router(ai_analysis_router)
app.include_router(crawler_router)
app.include_router(dashboard_router)
app.include_router(knowledge_router)
app.include_router(learning_router)
app.include_router(products_router)
app.include_router(ranking_router)
app.include_router(recommendations_router)
app.include_router(reports_router)
app.include_router(reviews_router)
app.include_router(stats_router)
app.include_router(strategy_router)
app.include_router(system_router)
app.include_router(metrics_router)
app.include_router(tasks_router)
app.include_router(selection_router)
app.include_router(shops_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "xuanpin-ai"}
