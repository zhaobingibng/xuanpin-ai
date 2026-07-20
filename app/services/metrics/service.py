"""MetricsService — Prometheus metrics collection for system monitoring."""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Singleton registry to avoid duplicate metric registration
_REGISTRY = CollectorRegistry()


# ── Counters ────────────────────────────────────────────────────

CRAWL_SUCCESS_TOTAL = Counter(
    "crawl_success_total",
    "Total number of successful crawl operations",
    registry=_REGISTRY,
)

CRAWL_FAILED_TOTAL = Counter(
    "crawl_failed_total",
    "Total number of failed crawl operations",
    registry=_REGISTRY,
)

SCHEDULER_TASK_TOTAL = Counter(
    "scheduler_task_total",
    "Total number of scheduled tasks executed",
    registry=_REGISTRY,
)

SCHEDULER_TASK_FAILED_TOTAL = Counter(
    "scheduler_task_failed_total",
    "Total number of failed scheduled tasks",
    registry=_REGISTRY,
)

DATABASE_QUERY_TOTAL = Counter(
    "database_query_total",
    "Total number of database queries",
    registry=_REGISTRY,
)

API_REQUEST_TOTAL = Counter(
    "api_request_total",
    "Total number of API requests",
    registry=_REGISTRY,
)

NOTIFICATION_SENT_TOTAL = Counter(
    "notification_sent_total",
    "Total number of notifications sent",
    registry=_REGISTRY,
)

BROWSER_RESTART_TOTAL = Counter(
    "browser_restart_total",
    "Total number of browser restarts",
    registry=_REGISTRY,
)


# ── Gauges ──────────────────────────────────────────────────────

CRAWLER_RUNNING = Gauge(
    "crawler_running",
    "Whether the crawler is currently running (1=running, 0=idle)",
    registry=_REGISTRY,
)

SCHEDULER_RUNNING = Gauge(
    "scheduler_running",
    "Whether the scheduler is currently running (1=running, 0=stopped)",
    registry=_REGISTRY,
)

ACTIVE_BROWSER_COUNT = Gauge(
    "active_browser_count",
    "Number of active browser instances",
    registry=_REGISTRY,
)

DATABASE_CONNECTION_COUNT = Gauge(
    "database_connection_count",
    "Number of active database connections",
    registry=_REGISTRY,
)


# ── Histograms ──────────────────────────────────────────────────

CRAWL_DURATION_SECONDS = Histogram(
    "crawl_duration_seconds",
    "Duration of crawl operations in seconds",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    registry=_REGISTRY,
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "api_request_duration_seconds",
    "Duration of API requests in seconds",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_REGISTRY,
)

DATABASE_QUERY_DURATION_SECONDS = Histogram(
    "database_query_duration_seconds",
    "Duration of database queries in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=_REGISTRY,
)


class MetricsService:
    """Prometheus 指标收集服务。

    Provides methods to increment counters, set gauges, and observe histograms.
    All metrics are registered in a singleton registry.
    """

    # ── Counter methods ─────────────────────────────────────

    @staticmethod
    def inc_crawl_success() -> None:
        """Increment successful crawl counter."""
        CRAWL_SUCCESS_TOTAL.inc()

    @staticmethod
    def inc_crawl_failed() -> None:
        """Increment failed crawl counter."""
        CRAWL_FAILED_TOTAL.inc()

    @staticmethod
    def inc_scheduler_task() -> None:
        """Increment scheduler task counter."""
        SCHEDULER_TASK_TOTAL.inc()

    @staticmethod
    def inc_scheduler_task_failed() -> None:
        """Increment failed scheduler task counter."""
        SCHEDULER_TASK_FAILED_TOTAL.inc()

    @staticmethod
    def inc_database_query() -> None:
        """Increment database query counter."""
        DATABASE_QUERY_TOTAL.inc()

    @staticmethod
    def inc_api_request() -> None:
        """Increment API request counter."""
        API_REQUEST_TOTAL.inc()

    @staticmethod
    def inc_notification_sent() -> None:
        """Increment notification sent counter."""
        NOTIFICATION_SENT_TOTAL.inc()

    @staticmethod
    def inc_browser_restart() -> None:
        """Increment browser restart counter."""
        BROWSER_RESTART_TOTAL.inc()

    # ── Gauge methods ───────────────────────────────────────

    @staticmethod
    def set_crawler_running(running: bool) -> None:
        """Set crawler running state (1=running, 0=idle)."""
        CRAWLER_RUNNING.set(1 if running else 0)

    @staticmethod
    def set_scheduler_running(running: bool) -> None:
        """Set scheduler running state (1=running, 0=stopped)."""
        SCHEDULER_RUNNING.set(1 if running else 0)

    @staticmethod
    def set_active_browser_count(count: int) -> None:
        """Set active browser count."""
        ACTIVE_BROWSER_COUNT.set(count)

    @staticmethod
    def set_database_connection_count(count: int) -> None:
        """Set database connection count."""
        DATABASE_CONNECTION_COUNT.set(count)

    # ── Histogram methods ───────────────────────────────────

    @staticmethod
    def observe_crawl_duration(duration_seconds: float) -> None:
        """Observe crawl duration."""
        CRAWL_DURATION_SECONDS.observe(duration_seconds)

    @staticmethod
    def observe_api_request_duration(duration_seconds: float) -> None:
        """Observe API request duration."""
        API_REQUEST_DURATION_SECONDS.observe(duration_seconds)

    @staticmethod
    def observe_database_query_duration(duration_seconds: float) -> None:
        """Observe database query duration."""
        DATABASE_QUERY_DURATION_SECONDS.observe(duration_seconds)

    # ── Export ───────────────────────────────────────────────

    @staticmethod
    def generate_metrics() -> bytes:
        """Generate Prometheus-format metrics output."""
        return generate_latest(_REGISTRY)

    @staticmethod
    def get_registry() -> CollectorRegistry:
        """Return the metrics registry."""
        return _REGISTRY
