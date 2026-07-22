"""Job registry — placeholder for future business task definitions.

Phase 44.1: no concrete business jobs yet. This module provides the
structure and a convenience function to list registered jobs.

Business jobs (crawl, matching, report generation, etc.) will be
defined elsewhere and registered via SchedulerManager.add_job().
"""

from __future__ import annotations


# ── Registry ──────────────────────────────────────────────────

# Future business jobs will be defined here or in app/tasks/.
# This dict provides a human-readable catalog for introspection.
# Format: {job_id: description}

_JOB_CATALOG: dict[str, str] = {
    # "daily_crawl":     "每日关键词采集",
    # "daily_selection": "每日选品流水线",
    # "daily_report":    "每日报告生成",
    # "supply_matching": "供应链匹配",
    # "health_check":    "系统健康检查",
}


def list_registered_jobs() -> dict[str, str]:
    """返回已注册到目录的业务任务清单。"""
    return dict(_JOB_CATALOG)


def register_job(job_id: str, description: str) -> None:
    """向目录注册一个任务说明（不影响 scheduler）。"""
    _JOB_CATALOG[job_id] = description
