"""Tests for Phase 44.2 — TaskRegistry business task registration layer.

Covers: register, unregister, get_task, list_tasks, sync_to_scheduler, integration.
"""

import asyncio

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.tasks.registry import TaskDefinition, TaskRegistry


# ── Test helpers ───────────────────────────────────────────────


async def _dummy_job_a() -> str:
    """Dummy job A."""
    await asyncio.sleep(0)
    return "a"


async def _dummy_job_b() -> str:
    """Dummy job B."""
    await asyncio.sleep(0)
    return "b"


# ═══════════════════════════════════════════════════════════════
# TaskDefinition
# ═══════════════════════════════════════════════════════════════


class TestTaskDefinition:
    """TaskDefinition 数据对象测试。"""

    def test_create_definition(self):
        """应能创建 TaskDefinition 实例。"""
        td = TaskDefinition(name="test", func=_dummy_job_a, trigger="cron", hour=8)
        assert td.name == "test"
        assert td.func is _dummy_job_a
        assert td.trigger == "cron"
        assert td.trigger_kwargs == {"hour": 8}
        assert td.enabled is True

    def test_definition_disabled(self):
        """enabled=False 时应正确记录。"""
        td = TaskDefinition(name="off", func=_dummy_job_a, enabled=False)
        assert td.enabled is False

    def test_definition_to_dict(self):
        """to_dict() 应返回正确的字典。"""
        td = TaskDefinition(name="dict_test", func=_dummy_job_a, trigger="interval", seconds=60)
        d = td.to_dict()
        assert d["name"] == "dict_test"
        assert d["func"] == "_dummy_job_a"
        assert "interval" in d["trigger"]
        assert d["trigger_kwargs"] == {"seconds": 60}
        assert d["enabled"] is True


# ═══════════════════════════════════════════════════════════════
# Register
# ═══════════════════════════════════════════════════════════════


class TestRegister:
    """register() 测试。"""

    def test_register_single_task(self):
        """注册单个任务，task_count 应为 1。"""
        registry = TaskRegistry()
        registry.register("job_a", _dummy_job_a, trigger="cron", hour=9)
        assert registry.task_count == 1

    def test_register_multiple_tasks(self):
        """注册多个任务，task_count 应正确递增。"""
        registry = TaskRegistry()
        registry.register("a", _dummy_job_a, trigger="interval", seconds=10)
        registry.register("b", _dummy_job_b, trigger="cron", hour=8)
        registry.register("c", _dummy_job_a, trigger="interval", minutes=30)
        assert registry.task_count == 3

    def test_register_returns_definition(self):
        """register() 应返回 TaskDefinition 对象。"""
        registry = TaskRegistry()
        td = registry.register("ret_test", _dummy_job_a, trigger="cron", hour=6)
        assert isinstance(td, TaskDefinition)
        assert td.name == "ret_test"
        assert td.func is _dummy_job_a

    def test_register_idempotent(self):
        """同名重复注册应覆盖旧定义（幂等）。"""
        registry = TaskRegistry()
        registry.register("dup", _dummy_job_a, trigger="cron", hour=1)
        registry.register("dup", _dummy_job_b, trigger="cron", hour=2)
        assert registry.task_count == 1
        td = registry.get_task("dup")
        assert td is not None
        assert td.func is _dummy_job_b  # should be the new one
        assert td.trigger_kwargs["hour"] == 2


# ═══════════════════════════════════════════════════════════════
# Unregister
# ═══════════════════════════════════════════════════════════════


class TestUnregister:
    """unregister() 测试。"""

    def test_unregister_existing(self):
        """注销已存在任务返回 True，task_count 减 1。"""
        registry = TaskRegistry()
        registry.register("to_delete", _dummy_job_a)
        assert registry.task_count == 1
        result = registry.unregister("to_delete")
        assert result is True
        assert registry.task_count == 0

    def test_unregister_nonexistent(self):
        """注销不存在任务返回 False。"""
        registry = TaskRegistry()
        result = registry.unregister("ghost")
        assert result is False

    def test_unregister_then_re_register(self):
        """注销后可重新注册同名任务。"""
        registry = TaskRegistry()
        registry.register("reuse", _dummy_job_a)
        registry.unregister("reuse")
        td = registry.register("reuse", _dummy_job_b)
        assert registry.task_count == 1
        assert td.func is _dummy_job_b


# ═══════════════════════════════════════════════════════════════
# Get
# ═══════════════════════════════════════════════════════════════


class TestGetTask:
    """get_task() 测试。"""

    def test_get_existing_task(self):
        """获取已存在任务应返回 TaskDefinition。"""
        registry = TaskRegistry()
        registry.register("find_me", _dummy_job_a, trigger="interval", seconds=5)
        td = registry.get_task("find_me")
        assert td is not None
        assert td.name == "find_me"
        assert td.trigger_kwargs == {"seconds": 5}

    def test_get_nonexistent_task(self):
        """获取不存在任务应返回 None。"""
        registry = TaskRegistry()
        td = registry.get_task("nobody")
        assert td is None

    def test_get_task_after_unregister(self):
        """注销后 get_task 应返回 None。"""
        registry = TaskRegistry()
        registry.register("gone", _dummy_job_a)
        registry.unregister("gone")
        assert registry.get_task("gone") is None


# ═══════════════════════════════════════════════════════════════
# List
# ═══════════════════════════════════════════════════════════════


class TestListTasks:
    """list_tasks() / list_enabled_tasks() 测试。"""

    def test_list_empty(self):
        """空 registry 应返回空列表。"""
        registry = TaskRegistry()
        assert registry.list_tasks() == []

    def test_list_with_tasks(self):
        """有任务时应返回正确数量的摘要。"""
        registry = TaskRegistry()
        registry.register("t1", _dummy_job_a, trigger="cron", hour=1)
        registry.register("t2", _dummy_job_b, trigger="interval", minutes=30)

        tasks = registry.list_tasks()
        assert len(tasks) == 2
        names = {t["name"] for t in tasks}
        assert names == {"t1", "t2"}

    def test_list_dict_structure(self):
        """list_tasks 每项应包含 name, func, trigger, trigger_kwargs, enabled。"""
        registry = TaskRegistry()
        registry.register("struct", _dummy_job_a, trigger="cron", hour=3)

        tasks = registry.list_tasks()
        task = tasks[0]
        for key in ("name", "func", "trigger", "trigger_kwargs", "enabled"):
            assert key in task, f"Missing key: {key}"

    def test_list_enabled_only(self):
        """list_enabled_tasks() 应只返回 enabled=True 的任务。"""
        registry = TaskRegistry()
        registry.register("on", _dummy_job_a, enabled=True)
        registry.register("off", _dummy_job_b, enabled=False)

        enabled = registry.list_enabled_tasks()
        assert len(enabled) == 1
        assert enabled[0].name == "on"

    def test_list_enabled_count(self):
        """list_enabled_tasks 数量 ≤ task_count。"""
        registry = TaskRegistry()
        registry.register("e1", _dummy_job_a, enabled=True)
        registry.register("e2", _dummy_job_a, enabled=False)
        registry.register("e3", _dummy_job_b, enabled=True)

        assert len(registry.list_enabled_tasks()) == 2
        assert registry.task_count == 3


# ═══════════════════════════════════════════════════════════════
# Sync to Scheduler
# ═══════════════════════════════════════════════════════════════


class TestSyncToScheduler:
    """sync_to_scheduler() 测试。"""

    def test_sync_empty_registry(self):
        """空 registry sync 应返回 0。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 0

    def test_sync_adds_jobs_to_scheduler(self):
        """sync 应把注册的任务添加到 SchedulerManager。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("sync_a", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))
        registry.register("sync_b", _dummy_job_b, trigger=IntervalTrigger(seconds=7200))

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 2
        assert mgr.job_count == 2

        jobs = mgr.get_jobs()
        job_ids = {j["id"] for j in jobs}
        assert "sync_a" in job_ids
        assert "sync_b" in job_ids

    def test_sync_skips_disabled_tasks(self):
        """sync 应跳过 enabled=False 的任务。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("active", _dummy_job_a, trigger=IntervalTrigger(seconds=3600), enabled=True)
        registry.register("inactive", _dummy_job_b, trigger=IntervalTrigger(seconds=7200), enabled=False)

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 1
        assert mgr.job_count == 1

        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "active" in job_ids
        assert "inactive" not in job_ids

    def test_remove_from_scheduler(self):
        """remove_from_scheduler 应从 scheduler 中移除任务。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("removable", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)
        assert mgr.job_count == 1

        result = registry.remove_from_scheduler(mgr, "removable")
        assert result is True
        assert mgr.job_count == 0

    def test_remove_from_scheduler_nonexistent(self):
        """移除不存在任务返回 False。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        mgr = SchedulerManager()
        result = registry.remove_from_scheduler(mgr, "nope")
        assert result is False


# ═══════════════════════════════════════════════════════════════
# Integration — Registry + SchedulerManager lifecycle
# ═══════════════════════════════════════════════════════════════


class TestRegistrySchedulerIntegration:
    """TaskRegistry + SchedulerManager 完整集成测试。"""

    @pytest.mark.anyio
    async def test_full_lifecycle(self):
        """注册 → sync → start → list → shutdown 完整流程。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("life_a", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))
        registry.register("life_b", _dummy_job_b, trigger=IntervalTrigger(seconds=7200))

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)

        assert mgr.job_count == 2

        mgr.start()
        try:
            jobs = mgr.get_jobs()
            assert len(jobs) == 2
            for job in jobs:
                assert job["name"] in ("life_a", "life_b")
        finally:
            mgr.shutdown(wait=False)

    @pytest.mark.anyio
    async def test_unregister_after_sync(self):
        """sync 后 unregister + remove_from_scheduler 应同时清除两端。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("gone", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)
        assert mgr.job_count == 1

        # Unregister from registry AND remove from scheduler
        registry.unregister("gone")
        registry.remove_from_scheduler(mgr, "gone")
        assert registry.task_count == 0
        assert mgr.job_count == 0

    @pytest.mark.anyio
    async def test_double_sync_is_idempotent(self):
        """两次 sync 不应创建重复任务（replace_existing）。"""
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        registry.register("uniq", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))

        mgr = SchedulerManager()
        registry.sync_to_scheduler(mgr)
        assert mgr.job_count == 1
        registry.sync_to_scheduler(mgr)
        assert mgr.job_count == 1  # still 1, not duplicated


# ═══════════════════════════════════════════════════════════════
# Multiple registries
# ═══════════════════════════════════════════════════════════════


class TestMultipleRegistries:
    """多个 TaskRegistry 实例互不干扰。"""

    def test_two_registries_independent(self):
        """两个 registry 独立管理各自任务。"""
        r1 = TaskRegistry()
        r2 = TaskRegistry()

        r1.register("r1_task", _dummy_job_a)
        r2.register("r2_task", _dummy_job_b)

        assert r1.task_count == 1
        assert r2.task_count == 1
        assert r1.get_task("r2_task") is None
        assert r2.get_task("r1_task") is None

    def test_two_registries_same_scheduler(self):
        """两个 registry 可以向同一个 scheduler sync 任务。"""
        from app.scheduler.scheduler import SchedulerManager

        r1 = TaskRegistry()
        r2 = TaskRegistry()
        r1.register("from_r1", _dummy_job_a, trigger=IntervalTrigger(seconds=3600))
        r2.register("from_r2", _dummy_job_b, trigger=IntervalTrigger(seconds=7200))

        mgr = SchedulerManager()
        r1.sync_to_scheduler(mgr)
        r2.sync_to_scheduler(mgr)

        assert mgr.job_count == 2
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "from_r1" in job_ids
        assert "from_r2" in job_ids
