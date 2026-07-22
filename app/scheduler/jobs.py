"""Job registry -- placeholder for future business task definitions.

Phase 44.1: no concrete business jobs yet. This module provides the
structure and a convenience function to list registered jobs.

Business jobs (crawl, matching, report generation, etc.) will be
defined elsewhere and registered via SchedulerManager.add_job().
"""

from __future__ import annotations


# -- Registry ------------------------------------------------------------------

# Future business jobs will be defined here or in app/tasks/.
# This dict provides a human-readable catalog for introspection.
# Format: {job_id: description}

_JOB_CATALOG: dict[str, str] = {}


def list_registered_jobs() -> dict[str, str]:
    """Return the job catalog."""
    return dict(_JOB_CATALOG)


def register_job(job_id: str, description: str) -> None:
    """Register a job description (does not affect scheduler)."""
    _JOB_CATALOG[job_id] = description
