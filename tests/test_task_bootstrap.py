"""Tests for Phase 45.2 — task bootstrap & scheduler wiring.

Covers:
- build_task_registry 登记全部 4 个 Phase 44 任务（名称/trigger/cron 时间）
- bootstrap_tasks 同步到真实 SchedulerManager（job 数 / job_id / 幂等）
- health check 任务透传 scheduler_manager
- main.py lifespan 闭环：启动后 _task_registry 已登记 + jobs 已进调度器
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler.scheduler import SchedulerManager
from app.tasks.bootstrap import bootstrap_tasks, build_task_registry
from app.tasks.registry import TaskRegistry

EXPECTED_TASKS = {
    "system_health_check": {"hour": 1, "minute": 0},
    "taobao_daily_collect": {"hour": 2, "minute": 0},
    "supplier_matching": {"hour": 4, "minute": 0},
    "daily_recommendation": {"hour": 6, "minute": 0},
}


# ═══════════════════════════════════════════════════════════════
# build_task_registry
# ═══════════════════════════════════════════════════════════════


class TestBuildRegistry:
    def test_returns_registry(self):
        registry = build_task_registry()
        assert isinstance(registry, TaskRegistry)

    def test_registers_all_four_tasks(self):
        registry = build_task_registry()
        assert registry.task_count == 4
        names = {t["name"] for t in registry.list_tasks()}
        assert names == set(EXPECTED_TASKS)

    def test_all_tasks_cron_with_expected_time(self):
        registry = build_task_registry()
        for name, kwargs in EXPECTED_TASKS.items():
            td = registry.get_task(name)
            assert td is not None
            assert td.trigger == "cron"
            assert td.trigger_kwargs == kwargs

    def test_all_tasks_enabled(self):
        registry = build_task_registry()
        assert len(registry.list_enabled_tasks()) == 4

    def test_all_funcs_are_coroutine_callables(self):
        registry = build_task_registry()
        import inspect

        for name in EXPECTED_TASKS:
            td = registry.get_task(name)
            assert inspect.iscoroutinefunction(td.func)

    def test_scheduler_manager_passed_to_health_check(self):
        """health check register 应收到 scheduler_manager 透传。"""
        sentinel = object()
        with patch(
            "app.tasks.health_check_task.register_health_check_task"
        ) as mock_health, patch(
            "app.tasks.taobao_collect_task.register_taobao_collect_task"
        ), patch(
            "app.tasks.supplier_matching_task.register_supplier_matching_task"
        ), patch(
            "app.tasks.recommendation_task.register_recommendation_task"
        ):
            build_task_registry(scheduler_manager=sentinel)
            mock_health.assert_called_once()
            assert mock_health.call_args.kwargs["scheduler_manager"] is sentinel


# ═══════════════════════════════════════════════════════════════
# bootstrap_tasks — 同步到真实 SchedulerManager
# ═══════════════════════════════════════════════════════════════


class TestBootstrapTasks:
    def test_sync_count_and_registry(self):
        mgr = SchedulerManager()
        registry, synced = bootstrap_tasks(mgr)

        assert isinstance(registry, TaskRegistry)
        assert synced == 4
        assert registry.task_count == 4

    def test_jobs_registered_in_manager(self):
        mgr = SchedulerManager()
        bootstrap_tasks(mgr)

        assert mgr.job_count == 4
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert job_ids == set(EXPECTED_TASKS)

    def test_idempotent_rebootstrap(self):
        """重复 bootstrap 到同一 manager 不产生重复 job（同 id 覆盖）。"""
        mgr = SchedulerManager()
        bootstrap_tasks(mgr)
        bootstrap_tasks(mgr)
        assert mgr.job_count == 4

    def test_does_not_start_scheduler(self):
        """bootstrap 只登记同步，不负责 start。"""
        mgr = SchedulerManager()
        bootstrap_tasks(mgr)
        assert mgr.running is False


# ═══════════════════════════════════════════════════════════════
# main.py lifespan 闭环
# ═══════════════════════════════════════════════════════════════


class TestLifespanWiring:
    @pytest.mark.anyio
    async def test_lifespan_bootstraps_and_syncs(self):
        import app.api.main as main

        # 保护：屏蔽旧 TaskScheduler 的真实 APScheduler 启动，聚焦新链路
        fake_legacy = MagicMock(name="TaskScheduler")
        fake_legacy.running = True

        with patch("app.tasks.scheduler.TaskScheduler", return_value=fake_legacy):
            async with main.lifespan(main.app):
                assert main._task_registry is not None
                assert main._task_registry.task_count == 4
                names = {t["name"] for t in main._task_registry.list_tasks()}
                assert names == set(EXPECTED_TASKS)

                assert main._scheduler_manager is not None
                job_ids = {j["id"] for j in main._scheduler_manager.get_jobs()}
                assert set(EXPECTED_TASKS).issubset(job_ids)

        # 关闭后清理
        assert main._scheduler_manager is None
        assert main._task_registry is None
