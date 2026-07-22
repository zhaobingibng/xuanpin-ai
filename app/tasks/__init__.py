"""Task scheduling module — APScheduler-based job management."""

from app.tasks.daily_selection_task import daily_selection_job, run_daily_selection_once
from app.tasks.execution_logger import TaskExecutionLogger
from app.tasks.context import TaskContext
from app.tasks.health_check_task import register_health_check_task, system_health_check
from app.tasks.jobs import auto_crawl_job, daily_crawl_job, daily_pipeline_job
from app.tasks.recommendation_task import (
    recommendation_task,
    register_recommendation_task,
)
from app.tasks.registry import TaskRegistry, TaskDefinition
from app.tasks.scheduler import TaskScheduler
from app.tasks.supplier_matching_task import (
    register_supplier_matching_task,
    supplier_matching_task,
)
from app.tasks.taobao_collect_task import (
    register_taobao_collect_task,
    taobao_daily_collect,
)

__all__ = [
    "TaskScheduler",
    "TaskRegistry",
    "TaskDefinition",
    "TaskContext",
    "TaskExecutionLogger",
    "system_health_check",
    "register_health_check_task",
    "taobao_daily_collect",
    "register_taobao_collect_task",
    "supplier_matching_task",
    "register_supplier_matching_task",
    "recommendation_task",
    "register_recommendation_task",
    "daily_crawl_job",
    "daily_pipeline_job",
    "auto_crawl_job",
    "daily_selection_job",
    "run_daily_selection_once",
]
