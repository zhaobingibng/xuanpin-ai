"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.products import router as products_router
from app.api.ranking import router as ranking_router
from app.api.stats import router as stats_router

app = FastAPI(title="xuanpin-ai API")

app.include_router(products_router)
app.include_router(ranking_router)
app.include_router(stats_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "xuanpin-ai"}
