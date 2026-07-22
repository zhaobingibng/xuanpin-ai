"""Tests for Phase 44.5 — supplier_matching_task (1688 自动匹配).

Covers:
- 任务调用链: ProductRepository.find_new_products → SupplierMatchingService
  .match_products_with_matcher → session.add/commit → ctx.set_result
- TaskContext result 结构 {total, matched, failed, duration}
- 异常处理: 单商品匹配失败弹性 / 会话致命异常
- registry 注册 (name=supplier_matching / cron / 04:00)
- scheduler 同步
- 闭环: 注册 func 执行返回 ctx.to_dict()

策略: mock repository + mock service，不写真实数据库。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.context import TaskContext
from app.tasks.registry import TaskRegistry
from app.tasks.supplier_matching_task import (
    register_supplier_matching_task,
    supplier_matching_task,
)

TASK_MODULE = "app.tasks.supplier_matching_task"


# ── Helpers ────────────────────────────────────────────────────


class _FakeSession:
    """最小异步会话：支持 async with + add/commit。"""

    def __init__(self) -> None:
        self.added: list = []
        self.commit = AsyncMock()

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def add(self, obj) -> None:
        self.added.append(obj)


def _fake_products(n: int):
    return [SimpleNamespace(id=i, name=f"p{i}", price=10.0 + i) for i in range(n)]


def _patch_env(products, match_side_effect=None, match_return=None, session=None):
    """构造 mock: settings / session_factory / ProductRepository / Service。

    返回 (context_managers_list, service_mock, session)。
    """
    session = session or _FakeSession()

    settings = SimpleNamespace(daily_crawl_limit=100)

    repo_instance = MagicMock(name="ProductRepository")
    repo_instance.find_new_products = AsyncMock(return_value=products)

    service_instance = MagicMock(name="SupplierMatchingService")
    if match_side_effect is not None:
        service_instance.match_products_with_matcher = AsyncMock(
            side_effect=match_side_effect
        )
    else:
        service_instance.match_products_with_matcher = AsyncMock(
            return_value=match_return if match_return is not None else []
        )

    patchers = [
        patch("app.config.settings.get_settings", return_value=settings),
        patch(
            "app.database.base.get_async_session_factory",
            return_value=lambda: session,
        ),
        patch(
            "app.database.product_repository.ProductRepository",
            return_value=repo_instance,
        ),
        patch(
            "app.services.supplier_matching.SupplierMatchingService",
            return_value=service_instance,
        ),
    ]
    return patchers, service_instance, repo_instance, session


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
        products = _fake_products(3)
        # 每个商品返回 1 条匹配
        patchers, service, repo, session = _patch_env(
            products, match_return=[SimpleNamespace(rank=1)]
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert set(ctx.result.keys()) == {"total", "matched", "failed", "duration"}
        assert ctx.result["total"] == 3
        assert ctx.result["matched"] == 3
        assert ctx.result["failed"] == 0
        assert isinstance(ctx.result["duration"], (int, float))
        assert ctx.completed is True
        assert ctx.error is None

    @pytest.mark.anyio
    async def test_service_called_per_product(self):
        products = _fake_products(2)
        patchers, service, repo, session = _patch_env(
            products, match_return=[SimpleNamespace(rank=1)]
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert service.match_products_with_matcher.await_count == 2
        # top_k 透传
        assert service.match_products_with_matcher.await_args.kwargs["top_k"] == 3

    @pytest.mark.anyio
    async def test_matches_added_and_committed(self):
        products = _fake_products(1)
        patchers, service, repo, session = _patch_env(
            products, match_return=[SimpleNamespace(rank=1), SimpleNamespace(rank=2)]
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        # 2 条匹配记录被 add
        assert len(session.added) == 2
        session.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_no_products(self):
        patchers, service, repo, session = _patch_env([], match_return=[])
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.result["total"] == 0
        assert ctx.result["matched"] == 0
        service.match_products_with_matcher.assert_not_awaited()
        session.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_product_without_match_not_counted(self):
        products = _fake_products(3)
        # 交替：有匹配 / 无匹配 / 有匹配
        patchers, service, repo, session = _patch_env(
            products,
            match_side_effect=[
                [SimpleNamespace(rank=1)],
                [],
                [SimpleNamespace(rank=1)],
            ],
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.result["total"] == 3
        assert ctx.result["matched"] == 2
        assert ctx.result["failed"] == 0

    @pytest.mark.anyio
    async def test_find_new_products_uses_limit(self):
        products = _fake_products(1)
        patchers, service, repo, session = _patch_env(
            products, match_return=[SimpleNamespace(rank=1)]
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        repo.find_new_products.assert_awaited_once()
        assert repo.find_new_products.await_args.kwargs["limit"] == 100


# ═══════════════════════════════════════════════════════════════
# 异常处理
# ═══════════════════════════════════════════════════════════════


class TestExceptionHandling:
    @pytest.mark.anyio
    async def test_single_product_match_failure_is_resilient(self):
        products = _fake_products(2)
        patchers, service, repo, session = _patch_env(
            products,
            match_side_effect=[RuntimeError("boom"), [SimpleNamespace(rank=1)]],
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.completed is True
        assert ctx.error is None
        assert ctx.result["total"] == 2
        assert ctx.result["matched"] == 1
        assert ctx.result["failed"] == 1
        session.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_commit_failure_sets_error(self):
        products = _fake_products(1)
        session = _FakeSession()
        session.commit = AsyncMock(side_effect=RuntimeError("db down"))
        patchers, service, repo, _ = _patch_env(
            products, match_return=[SimpleNamespace(rank=1)], session=session
        )
        ctx = TaskContext(task_name="supplier_matching")
        _enter(patchers)
        try:
            await supplier_matching_task(ctx)
        finally:
            _exit(patchers)

        assert ctx.completed is True
        assert ctx.error is not None
        assert "db down" in ctx.error
        assert ctx.result is None


# ═══════════════════════════════════════════════════════════════
# Registry 注册
# ═══════════════════════════════════════════════════════════════


class TestRegistration:
    def test_task_name(self):
        registry = TaskRegistry()
        td = register_supplier_matching_task(registry)
        assert td.name == "supplier_matching"

    def test_trigger_cron_0400(self):
        registry = TaskRegistry()
        td = register_supplier_matching_task(registry)
        assert td.trigger == "cron"
        assert td.trigger_kwargs == {"hour": 4, "minute": 0}

    def test_registered_in_registry(self):
        registry = TaskRegistry()
        register_supplier_matching_task(registry)
        assert registry.get_task("supplier_matching") is not None


# ═══════════════════════════════════════════════════════════════
# Scheduler 同步
# ═══════════════════════════════════════════════════════════════


class TestSchedulerSync:
    def test_sync_success(self):
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        register_supplier_matching_task(registry)

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 1
        assert mgr.job_count == 1
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "supplier_matching" in job_ids


# ═══════════════════════════════════════════════════════════════
# 闭环: 注册 func 执行返回 ctx.to_dict()
# ═══════════════════════════════════════════════════════════════


class TestClosedLoop:
    @pytest.mark.anyio
    async def test_registered_func_returns_context_dict(self):
        products = _fake_products(2)
        patchers, service, repo, session = _patch_env(
            products, match_return=[SimpleNamespace(rank=1)]
        )

        async def _fake_execute(name, func, *args, **kwargs):
            return await func(*args, **kwargs)

        registry = TaskRegistry()
        register_supplier_matching_task(registry)
        td = registry.get_task("supplier_matching")

        _enter(patchers)
        try:
            with patch(
                "app.tasks.execution_logger.TaskExecutionLogger.execute",
                side_effect=_fake_execute,
            ):
                result = await td.func()
        finally:
            _exit(patchers)

        assert result["task_name"] == "supplier_matching"
        assert result["completed"] is True
        assert result["result"]["total"] == 2
        assert result["result"]["matched"] == 2
