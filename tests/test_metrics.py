"""Tests for Phase 9.8 — MetricsService and Prometheus metrics API.

Covers: Counters, Gauges, Histograms, API Endpoint, concurrent access,
empty metrics, multiple increments, exception cases.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.services.metrics.service import (
    API_REQUEST_DURATION_SECONDS,
    API_REQUEST_TOTAL,
    ACTIVE_BROWSER_COUNT,
    BROWSER_RESTART_TOTAL,
    CRAWL_DURATION_SECONDS,
    CRAWL_FAILED_TOTAL,
    CRAWL_SUCCESS_TOTAL,
    CRAWLER_RUNNING,
    DATABASE_CONNECTION_COUNT,
    DATABASE_QUERY_DURATION_SECONDS,
    DATABASE_QUERY_TOTAL,
    NOTIFICATION_SENT_TOTAL,
    SCHEDULER_RUNNING,
    SCHEDULER_TASK_FAILED_TOTAL,
    SCHEDULER_TASK_TOTAL,
    MetricsService,
    _REGISTRY,
)


# ── Helpers ────────────────────────────────────────────────────


def _get_counter_value(counter) -> float:
    """Get current value of a counter."""
    return counter._value.get()


def _get_gauge_value(gauge) -> float:
    """Get current value of a gauge."""
    return gauge._value.get()


def _get_histogram_count(histogram) -> int:
    """Get sample count of a histogram."""
    return histogram._sum.get()


# ── TestCounters ────────────────────────────────────────────────


class TestCounters:
    """Counter metrics increment correctly."""

    def test_crawl_success_counter(self):
        initial = _get_counter_value(CRAWL_SUCCESS_TOTAL)
        MetricsService.inc_crawl_success()
        assert _get_counter_value(CRAWL_SUCCESS_TOTAL) == initial + 1

    def test_crawl_failed_counter(self):
        initial = _get_counter_value(CRAWL_FAILED_TOTAL)
        MetricsService.inc_crawl_failed()
        assert _get_counter_value(CRAWL_FAILED_TOTAL) == initial + 1

    def test_scheduler_task_counter(self):
        initial = _get_counter_value(SCHEDULER_TASK_TOTAL)
        MetricsService.inc_scheduler_task()
        assert _get_counter_value(SCHEDULER_TASK_TOTAL) == initial + 1

    def test_scheduler_task_failed_counter(self):
        initial = _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL)
        MetricsService.inc_scheduler_task_failed()
        assert _get_counter_value(SCHEDULER_TASK_FAILED_TOTAL) == initial + 1

    def test_database_query_counter(self):
        initial = _get_counter_value(DATABASE_QUERY_TOTAL)
        MetricsService.inc_database_query()
        assert _get_counter_value(DATABASE_QUERY_TOTAL) == initial + 1

    def test_api_request_counter(self):
        initial = _get_counter_value(API_REQUEST_TOTAL)
        MetricsService.inc_api_request()
        assert _get_counter_value(API_REQUEST_TOTAL) == initial + 1

    def test_notification_sent_counter(self):
        initial = _get_counter_value(NOTIFICATION_SENT_TOTAL)
        MetricsService.inc_notification_sent()
        assert _get_counter_value(NOTIFICATION_SENT_TOTAL) == initial + 1

    def test_browser_restart_counter(self):
        initial = _get_counter_value(BROWSER_RESTART_TOTAL)
        MetricsService.inc_browser_restart()
        assert _get_counter_value(BROWSER_RESTART_TOTAL) == initial + 1


# ── TestGauges ──────────────────────────────────────────────────


class TestGauges:
    """Gauge metrics set correctly."""

    def test_crawler_running_true(self):
        MetricsService.set_crawler_running(True)
        assert _get_gauge_value(CRAWLER_RUNNING) == 1.0

    def test_crawler_running_false(self):
        MetricsService.set_crawler_running(False)
        assert _get_gauge_value(CRAWLER_RUNNING) == 0.0

    def test_scheduler_running_true(self):
        MetricsService.set_scheduler_running(True)
        assert _get_gauge_value(SCHEDULER_RUNNING) == 1.0

    def test_scheduler_running_false(self):
        MetricsService.set_scheduler_running(False)
        assert _get_gauge_value(SCHEDULER_RUNNING) == 0.0

    def test_active_browser_count(self):
        MetricsService.set_active_browser_count(5)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == 5.0

    def test_active_browser_count_zero(self):
        MetricsService.set_active_browser_count(0)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == 0.0

    def test_database_connection_count(self):
        MetricsService.set_database_connection_count(10)
        assert _get_gauge_value(DATABASE_CONNECTION_COUNT) == 10.0


# ── TestHistograms ──────────────────────────────────────────────


class TestHistograms:
    """Histogram metrics observe correctly."""

    def test_crawl_duration(self):
        initial_sum = _get_histogram_count(CRAWL_DURATION_SECONDS)
        MetricsService.observe_crawl_duration(1.5)
        new_sum = _get_histogram_count(CRAWL_DURATION_SECONDS)
        assert new_sum > initial_sum

    def test_api_request_duration(self):
        initial_sum = _get_histogram_count(API_REQUEST_DURATION_SECONDS)
        MetricsService.observe_api_request_duration(0.05)
        new_sum = _get_histogram_count(API_REQUEST_DURATION_SECONDS)
        assert new_sum > initial_sum

    def test_database_query_duration(self):
        initial_sum = _get_histogram_count(DATABASE_QUERY_DURATION_SECONDS)
        MetricsService.observe_database_query_duration(0.001)
        new_sum = _get_histogram_count(DATABASE_QUERY_DURATION_SECONDS)
        assert new_sum > initial_sum

    def test_crawl_duration_multiple_observations(self):
        for duration in [0.1, 0.5, 1.0, 5.0, 10.0]:
            MetricsService.observe_crawl_duration(duration)
        # Just verify no exception raised


# ── TestMetricsService ──────────────────────────────────────────


class TestMetricsService:
    """MetricsService methods work correctly."""

    def test_generate_metrics_returns_bytes(self):
        output = MetricsService.generate_metrics()
        assert isinstance(output, bytes)

    def test_generate_metrics_contains_metrics(self):
        # Increment a counter first
        MetricsService.inc_crawl_success()
        output = MetricsService.generate_metrics().decode("utf-8")
        assert "crawl_success_total" in output

    def test_get_registry(self):
        registry = MetricsService.get_registry()
        assert registry is _REGISTRY

    def test_empty_metrics(self):
        # Generate metrics without any increments (except previous tests)
        output = MetricsService.generate_metrics()
        assert output is not None
        assert len(output) > 0


# ── TestMultipleIncrements ──────────────────────────────────────


class TestMultipleIncrements:
    """Multiple increments accumulate correctly."""

    def test_multiple_counter_increments(self):
        initial = _get_counter_value(CRAWL_SUCCESS_TOTAL)
        for _ in range(5):
            MetricsService.inc_crawl_success()
        assert _get_counter_value(CRAWL_SUCCESS_TOTAL) == initial + 5

    def test_gauge_can_be_updated_multiple_times(self):
        MetricsService.set_active_browser_count(1)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == 1.0
        MetricsService.set_active_browser_count(3)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == 3.0
        MetricsService.set_active_browser_count(0)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == 0.0


# ── TestConcurrentAccess ────────────────────────────────────────


class TestConcurrentAccess:
    """Metrics can be updated concurrently without errors."""

    @pytest.mark.anyio
    async def test_concurrent_counter_increments(self):
        initial = _get_counter_value(API_REQUEST_TOTAL)

        async def increment():
            for _ in range(10):
                MetricsService.inc_api_request()

        # Run 5 concurrent tasks
        await asyncio.gather(*[increment() for _ in range(5)])

        # Should have incremented by 50
        assert _get_counter_value(API_REQUEST_TOTAL) == initial + 50

    @pytest.mark.anyio
    async def test_concurrent_gauge_updates(self):
        async def update_gauge(value: int):
            MetricsService.set_active_browser_count(value)

        # Run concurrent updates
        await asyncio.gather(*[update_gauge(i) for i in range(10)])
        # Just verify no exception raised


# ── TestMetricsAPI ──────────────────────────────────────────────


class TestMetricsAPI:
    """GET /metrics API endpoint."""

    @pytest.mark.anyio
    async def test_metrics_endpoint(self):
        from app.api.metrics import metrics

        response = await metrics()
        assert response.status_code == 200
        assert "text/plain" in response.media_type
        assert b"crawl_success_total" in response.body or b"scheduler_running" in response.body

    @pytest.mark.anyio
    async def test_metrics_endpoint_increments_api_counter(self):
        from app.api.metrics import metrics

        initial = _get_counter_value(API_REQUEST_TOTAL)
        await metrics()
        assert _get_counter_value(API_REQUEST_TOTAL) == initial + 1


# ── TestIntegration ─────────────────────────────────────────────


class TestIntegration:
    """Metrics integration with other services."""

    @pytest.mark.anyio
    async def test_health_service_updates_gauges(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.health.service import HealthService

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())

        svc = HealthService(session, scheduler_running=True)

        with patch.object(svc, "_check_crawler", return_value={"ok": True, "last_crawl": None}):
            await svc.check()

        # Verify gauges were updated
        assert _get_gauge_value(SCHEDULER_RUNNING) == 1.0
        assert _get_gauge_value(CRAWLER_RUNNING) == 1.0

    @pytest.mark.anyio
    async def test_notification_service_increments_counter(self):
        from app.services.notification.service import NotificationService

        initial = _get_counter_value(NOTIFICATION_SENT_TOTAL)
        svc = NotificationService()
        await svc.notify("TEST", "test message")
        assert _get_counter_value(NOTIFICATION_SENT_TOTAL) == initial + 1


# ── TestExceptionCases ──────────────────────────────────────────


class TestExceptionCases:
    """Metrics handle edge cases gracefully."""

    def test_negative_gauge_value(self):
        # Gauges can technically be set to negative values
        MetricsService.set_active_browser_count(-1)
        assert _get_gauge_value(ACTIVE_BROWSER_COUNT) == -1.0
        # Reset to valid value
        MetricsService.set_active_browser_count(0)

    def test_zero_duration_observation(self):
        # Should not raise
        MetricsService.observe_crawl_duration(0.0)

    def test_large_duration_observation(self):
        # Should not raise
        MetricsService.observe_crawl_duration(10000.0)

    def test_generate_metrics_multiple_times(self):
        # Should not raise
        for _ in range(3):
            output = MetricsService.generate_metrics()
            assert output is not None
