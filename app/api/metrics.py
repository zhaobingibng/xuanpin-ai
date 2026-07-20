"""Metrics API — Prometheus metrics endpoint."""

from fastapi import APIRouter
from fastapi.responses import Response

from app.services.metrics.service import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Return Prometheus-format metrics.

    Standard endpoint for Prometheus scraping.
    Returns text/plain with all registered metrics.
    """
    MetricsService.inc_api_request()
    metrics_output = MetricsService.generate_metrics()
    return Response(
        content=metrics_output,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
