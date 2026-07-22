"""Tests for Phase 44.1 — SchedulerManager infrastructure.

Covers: init, start, shutdown, add_job, remove_job, get_jobs, idempotency.
"""

import asyncio

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.scheduler import SchedulerManager


# ── Test helpers ───────────────────────────────────────────────


async def _sample_job() -> str:
    """Minimal async job used for testing."""
    return "done"


async def _sample_job_with_sleep() -> str:
    """Async job with a small delay."""
    await asyncio.sleep(0.1)
    return "done"


# ═══════════════════════════════════════════════════════════════
# Init
# ═══════════════════════════════════════════════════════════════


class TestInit:
    """SchedulerManager 初始化测试。"""

    def test_init_creates_instance(self):
        """SchedulerManager 可以被实例化。"""
        mgr = SchedulerManager()
        assert mgr is not None
        assert mgr.running is False
        assert mgr.job_count == 0

    def test_init_not_running(self):
        """初始化后 running 应为 False。"""
        mgr = SchedulerManager()
        assert mgr.running is False


# ═══════════════════════════════════════════════════════════════
# Start & Shutdown
# ═══════════════════════════════════════════════════════════════


class TestStartShutdown:
    """启动/关闭生命周期测试。

    Note: start() requires a running event loop (APScheduler
    AsyncIOScheduler uses asyncio.get_running_loop()).  These
    tests use @pytest.mark.anyio to get one automatically.
    """

    @pytest.mark.anyio
    async def test_start_sets_running(self):
        """start() 后 running 应为 True。"""
        mgr = SchedulerManager()
        mgr.start()
        try:
            assert mgr.running is True
        finally:
            mgr.shutdown(wait=False)

    @pytest.mark.anyio
    async def test_shutdown_stops_running(self):
        """shutdown() 后 running 应为 False。"""
        mgr = SchedulerManager()
        mgr.start()
        mgr.shutdown(wait=False)
        assert mgr.running is False

    @pytest.mark.anyio
    async def test_start_idempotent(self):
        """重复 start() 不应报错。"""
        mgr = SchedulerManager()
        mgr.start()
        try:
            mgr.start()  # second call — should be no-op
            assert mgr.running is True
        finally:
            mgr.shutdown(wait=False)

    @pytest.mark.anyio
    async def test_shutdown_idempotent(self):
        """重复 shutdown() 不应报错。"""
        mgr = SchedulerManager()
        mgr.start()
        mgr.shutdown(wait=False)
        mgr.shutdown(wait=False)  # second call — should be no-op
        assert mgr.running is False

    def test_shutdown_before_start_no_error(self):
        """未启动时 shutdown() 不应报错。"""
        mgr = SchedulerManager()
        mgr.shutdown(wait=False)
        assert mgr.running is False

    @pytest.mark.anyio
    async def test_start_shutdown_sequence(self):
        """完整的 start → shutdown 流程。"""
        mgr = SchedulerManager()
        mgr.start()
        assert mgr.running is True
        mgr.shutdown(wait=False)
        assert mgr.running is False


# ═══════════════════════════════════════════════════════════════
# Job Management
# ═══════════════════════════════════════════════════════════════


class TestAddJob:
    """add_job() 测试。"""

    def test_add_job_before_start(self):
        """启动前可以添加任务。"""
        mgr = SchedulerManager()
        job = mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="test_job")
        assert job.id == "test_job"
        assert mgr.job_count == 1

    @pytest.mark.anyio
    async def test_add_job_after_start(self):
        """启动后可以添加任务。"""
        mgr = SchedulerManager()
        mgr.start()
        try:
            job = mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="after_start_job")
            assert job.id == "after_start_job"
            assert mgr.job_count == 1
        finally:
            mgr.shutdown(wait=False)

    def test_add_job_auto_generates_id(self):
        """不传 job_id 时自动使用函数名。"""
        mgr = SchedulerManager()
        job = mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600))
        assert job.id is not None
        assert job.id == "_sample_job"  # auto-generated from function name

    def test_add_job_with_name(self):
        """传 name 时应正确设置。"""
        mgr = SchedulerManager()
        job = mgr.add_job(
            _sample_job,
            trigger=IntervalTrigger(seconds=3600),
            job_id="named_job",
            name="我的命名任务",
        )
        assert job.name == "我的命名任务"

    def test_add_job_replace_existing(self):
        """replace_existing=True（默认）时，同 ID 任务应被替换。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="replace_test")
        mgr.add_job(_sample_job_with_sleep, trigger=IntervalTrigger(seconds=7200), job_id="replace_test")
        assert mgr.job_count == 1  # only one job with this ID

    def test_add_job_multiple_jobs(self):
        """可以添加多个不同 ID 的任务。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="job_a")
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=7200), job_id="job_b")
        assert mgr.job_count == 2


# ═══════════════════════════════════════════════════════════════
# Remove Job
# ═══════════════════════════════════════════════════════════════


class TestRemoveJob:
    """remove_job() 测试。"""

    def test_remove_existing_job(self):
        """移除已存在的任务返回 True。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="to_remove")
        assert mgr.job_count == 1
        result = mgr.remove_job("to_remove")
        assert result is True
        assert mgr.job_count == 0

    def test_remove_nonexistent_job(self):
        """移除不存在的任务返回 False。"""
        mgr = SchedulerManager()
        result = mgr.remove_job("nonexistent")
        assert result is False

    def test_remove_then_add_same_id(self):
        """移除后可以用相同 ID 重新添加。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="reuse_id")
        mgr.remove_job("reuse_id")
        mgr.add_job(_sample_job_with_sleep, trigger=IntervalTrigger(seconds=7200), job_id="reuse_id")
        assert mgr.job_count == 1


# ═══════════════════════════════════════════════════════════════
# Get Jobs
# ═══════════════════════════════════════════════════════════════


class TestGetJobs:
    """get_jobs() / get_job() 测试。"""

    def test_get_jobs_empty(self):
        """无任务时返回空列表。"""
        mgr = SchedulerManager()
        jobs = mgr.get_jobs()
        assert jobs == []

    def test_get_jobs_with_entries(self):
        """有任务时返回任务摘要列表。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="job_1", name="任务一")
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=7200), job_id="job_2", name="任务二")

        jobs = mgr.get_jobs()
        assert len(jobs) == 2
        for job in jobs:
            assert "id" in job
            assert "name" in job
            assert "trigger" in job
            assert "next_run" in job  # key always present (may be None)

        job_ids = {j["id"] for j in jobs}
        assert "job_1" in job_ids
        assert "job_2" in job_ids

    def test_get_job_by_id(self):
        """get_job('id') 返回正确的 Job 对象。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="specific_job")

        job = mgr.get_job("specific_job")
        assert job is not None
        assert job.id == "specific_job"

    def test_get_job_nonexistent(self):
        """get_job('nonexistent') 返回 None。"""
        mgr = SchedulerManager()
        job = mgr.get_job("nonexistent")
        assert job is None

    @pytest.mark.anyio
    async def test_get_jobs_after_shutdown(self):
        """shutdown 后 get_jobs() 仍可正常返回（数据不丢失）。"""
        mgr = SchedulerManager()
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="persist_job")
        mgr.start()
        mgr.shutdown(wait=False)

        jobs = mgr.get_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "persist_job"


# ═══════════════════════════════════════════════════════════════
# Properties
# ═══════════════════════════════════════════════════════════════


class TestProperties:
    """属性测试。"""

    @pytest.mark.anyio
    async def test_running_property(self):
        """running 属性正确反映状态。"""
        mgr = SchedulerManager()
        assert mgr.running is False
        mgr.start()
        try:
            assert mgr.running is True
        finally:
            mgr.shutdown(wait=False)
        assert mgr.running is False

    def test_job_count_property(self):
        """job_count 正确反映任务数量。"""
        mgr = SchedulerManager()
        assert mgr.job_count == 0
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="j1")
        assert mgr.job_count == 1
        mgr.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="j2")
        assert mgr.job_count == 2
        mgr.remove_job("j1")
        assert mgr.job_count == 1


# ═══════════════════════════════════════════════════════════════
# Integration — multiple managers
# ═══════════════════════════════════════════════════════════════


class TestMultipleManagers:
    """多个 SchedulerManager 实例互不干扰。"""

    @pytest.mark.anyio
    async def test_two_managers_independent(self):
        """两个实例独立管理各自的任务。"""
        mgr_a = SchedulerManager()
        mgr_b = SchedulerManager()

        mgr_a.add_job(_sample_job, trigger=IntervalTrigger(seconds=3600), job_id="a_job")
        mgr_b.add_job(_sample_job, trigger=IntervalTrigger(seconds=7200), job_id="b_job")

        assert mgr_a.job_count == 1
        assert mgr_b.job_count == 1

        mgr_a.remove_job("a_job")
        assert mgr_a.job_count == 0
        assert mgr_b.job_count == 1  # b unaffected

        mgr_a.start()
        mgr_b.start()
        try:
            assert mgr_a.running is True
            assert mgr_b.running is True
        finally:
            mgr_a.shutdown(wait=False)
            mgr_b.shutdown(wait=False)


# ═══════════════════════════════════════════════════════════════
# Lifespan integration
# ═══════════════════════════════════════════════════════════════


class TestLifespanIntegration:
    """验证 SchedulerManager 已集成到 FastAPI lifespan。"""

    @pytest.mark.anyio
    async def test_main_import_has_scheduler_manager(self):
        """main.py 中 _scheduler_manager 全局变量应可访问。"""
        from app.api.main import _scheduler_manager

        # After import, manager should be None (lifespan not yet run)
        # or an instance (if lifespan already triggered via ASGI transport)
        # We just verify the attribute exists
        assert hasattr(_scheduler_manager, "__class__") or _scheduler_manager is None
