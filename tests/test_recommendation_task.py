"""Tests for Phase 44.6 — recommendation_task (每日自动推荐).

Covers:
- 任务调用链: DailyRecommendationService.generate → ctx.set_result
- TaskContext result 结构 {total, recommended, failed, duration}
- 异常处理: generate 致命异常 → ctx.set_error
- registry 注册 (name=daily_recommendation / cron / 06:00)
- scheduler 同步
- 闭环: 注册 func 执行返回 ctx.to_dict()

策略: mock service (不修改 Service)，不写真实数据库。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.context import TaskContext
from app.tasks.recommendation_task import (
    recommendation_task,
    register_recommendation_task,
)
from app.tasks.registry import TaskRegistry

TASK_MODULE = "app.tasks.recommendation_task"


# ── Helpers ────────────────────────────────────────────────────


class _FakeSession:
    """最小异步会话：支持 async with。"""

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


def _fake_report(total=3, items=None, date="2026-07-21"):
    if items is None:
        items = [{"product_id": i} for i in range(total)]
    return {"date": date, "total": total, "items": items}


def _patch_env(generate_return=None, generate_side_effect=None, session=None):
    """构造 mock: session_factory / DailyRecommendationService。

    返回 (patchers, service_instance)。
    """
    session = session or _FakeSession()

    service_instance = MagicMock(name="DailyRecommendationService")
    if generate_side_effect is not None:
        service_instance.generate = AsyncMock(side_effect=generate_side_effect)
    else:
        service_instance.generate = AsyncMock(
            return_value=generate_return
            if generate_return is not None
            else _fake_report()
        )

    patchers = [
        patch(
            "app.database.base.get_async_session_factory",
            return_value=lambda: session,
        ),
        patch(
            "app.services.recommendation.daily_recommendation."
            "DailyRecommendationService",
            return_value=service_instance,
        ),
    ]
    return patchers, service_instance


def _enter(patchers):
    for p in patchers:
        p.start()


def _exit(patchers):
    for p in patchers:
        p.stop()


# ═══════════════════════════════════════════════════════════════
# 调用链 & result 结构
# ═══════════════════════════════════════════════════════════════


class TestCallChain:
    @pytest.mark.anyio
    async def test_success_result_structure(self):
        patchers, service = _patch_env(generate_return=_fake_report(total=3))
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert set(ctx.result.keys()) == {
            "total",
            "recommended",
            "failed",
            "duration",
        }
        assert ctx.result["total"] == 3
        assert ctx.result["recommended"] == 3
        assert ctx.result["failed"] == 0
        assert isinstance(ctx.result["duration"], (int, float))
        assert ctx.completed is True
        assert ctx.error is None

    @pytest.mark.anyio
    async def test_generate_called_once(self):
        patchers, service = _patch_env(generate_return=_fake_report())
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        service.generate.assert_awaited_once()

    @pytest.mark.anyio
    async def test_empty_recommendation(self):
        patchers, service = _patch_env(
            generate_return=_fake_report(total=0, items=[])
        )
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.result["total"] == 0
        assert ctx.result["recommended"] == 0
        assert ctx.result["failed"] == 0

    @pytest.mark.anyio
    async def test_failed_counts_missing_items(self):
        # total 声明 5 但仅生成 3 条 items → failed=2
        patchers, service = _patch_env(
            generate_return=_fake_report(
                total=5, items=[{"product_id": i} for i in range(3)]
            )
        )
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.result["total"] == 5
        assert ctx.result["recommended"] == 3
        assert ctx.result["failed"] == 2

    @pytest.mark.anyio
    async def test_date_metadata_recorded(self):
        patchers, service = _patch_env(
            generate_return=_fake_report(date="2026-07-21")
        )
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.get_metadata("date") == "2026-07-21"


# ═══════════════════════════════════════════════════════════════
# 异常处理
# ═══════════════════════════════════════════════════════════════


class TestExceptionHandling:
    @pytest.mark.anyio
    async def test_generate_failure_sets_error(self):
        patchers, service = _patch_env(
            generate_side_effect=RuntimeError("gen down")
        )
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.completed is True
        assert ctx.error is not None
        assert "gen down" in ctx.error
        assert ctx.result is None

    @pytest.mark.anyio
    async def test_error_records_duration(self):
        patchers, service = _patch_env(
            generate_side_effect=RuntimeError("boom")
        )
        ctx = TaskContext(task_name="daily_recommendation")
        _enter(patchers)
        try:
            await recommendation_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.get_metadata("duration") is not None


# ═══════════════════════════════════════════════════════════════
# Registry 注册
# ═══════════════════════════════════════════════════════════════


class TestRegistration:
    def test_task_name(self):
        registry = TaskRegistry()
        td = register_recommendation_task(registry)
        assert td.name == "daily_recommendation"

    def test_trigger_cron_0600(self):
        registry = TaskRegistry()
        td = register_recommendation_task(registry)
        assert td.trigger == "cron"
        assert td.trigger_kwargs == {"hour": 6, "minute": 0}

    def test_registered_in_registry(self):
        registry = TaskRegistry()
        register_recommendation_task(registry)
        assert registry.get_task("daily_recommendation") is not None


# ═══════════════════════════════════════════════════════════════
# Scheduler 同步
# ═══════════════════════════════════════════════════════════════


class TestSchedulerSync:
    def test_sync_success(self):
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        register_recommendation_task(registry)

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 1
        assert mgr.job_count == 1
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "daily_recommendation" in job_ids


# ═══════════════════════════════════════════════════════════════
# 闭环: 注册 func 执行返回 ctx.to_dict()
# ═══════════════════════════════════════════════════════════════


class TestClosedLoop:
    @pytest.mark.anyio
    async def test_registered_func_returns_context_dict(self):
        patchers, service = _patch_env(generate_return=_fake_report(total=2))

        async def _fake_execute(name, func, *args, **kwargs):
            return await func(*args, **kwargs)

        registry = TaskRegistry()
        register_recommendation_task(registry)
        td = registry.get_task("daily_recommendation")

        _enter(patchers)
        try:
            with patch(
                "app.tasks.execution_logger.TaskExecutionLogger.execute",
                side_effect=_fake_execute,
            ):
                result = await td.func()
        finally:
            _exit(patchers)

        assert result["task_name"] == "daily_recommendation"
        assert result["completed"] is True
        assert result["result"]["total"] == 2
        assert result["result"]["recommended"] == 2
