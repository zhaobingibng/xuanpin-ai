"""Tests for Phase 44.4.1.2 — taobao_daily_collect real integration.

Covers:
- 任务调用链: TaobaoCrawler.crawl_with_metrics → _save_products → ctx.set_result
- TaskContext result 结构 {total, success, failed, duration}
- 异常处理: 单关键词采集失败弹性 / 保存致命异常
- registry 注册不变 (name / cron / 02:00)
- scheduler 同步

策略: mock crawler + mock repository(_save_products / ProductService)，
不启动真实浏览器、不写真实数据库。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.context import TaskContext
from app.tasks.registry import TaskRegistry
from app.tasks.taobao_collect_task import (
    register_taobao_collect_task,
    taobao_daily_collect,
)

TASK_MODULE = "app.tasks.taobao_collect_task"


# ── Helpers ────────────────────────────────────────────────────


def _fake_products(n: int) -> list[SimpleNamespace]:
    """构造 n 个假 RawProduct（仅需被计数）。"""
    return [SimpleNamespace(name=f"p{i}") for i in range(n)]


def _make_crawler(crawl_return=None, crawl_side_effect=None):
    """构造一个 mock TaobaoCrawler 实例。"""
    crawler = MagicMock(name="TaobaoCrawler")
    if crawl_side_effect is not None:
        crawler.crawl_with_metrics = AsyncMock(side_effect=crawl_side_effect)
    else:
        crawler.crawl_with_metrics = AsyncMock(return_value=crawl_return)
    crawler.close = AsyncMock()
    return crawler


def _patch_settings(keywords=("海苔卷",), limit=10):
    """patch get_settings 返回受控关键词/限额。"""
    settings = SimpleNamespace(crawl_keywords=list(keywords), daily_crawl_limit=limit)
    return patch("app.config.settings.get_settings", return_value=settings)


# ═══════════════════════════════════════════════════════════════
# 调用链 & result 结构
# ═══════════════════════════════════════════════════════════════


class TestCallChain:
    """验证 TaskContext → crawler → save → set_result 调用链。"""

    @pytest.mark.anyio
    async def test_success_flow_result_structure(self):
        crawl_result = SimpleNamespace(products=_fake_products(3), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(return_value={"saved_count": 3, "failed_count": 0})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        # result 结构完整
        assert set(ctx.result.keys()) == {"total", "success", "failed", "duration"}
        assert ctx.result["total"] == 3
        assert ctx.result["success"] == 3
        assert ctx.result["failed"] == 0
        assert isinstance(ctx.result["duration"], (int, float))
        assert ctx.completed is True
        assert ctx.error is None

    @pytest.mark.anyio
    async def test_crawler_called_with_keyword_and_limit(self):
        crawl_result = SimpleNamespace(products=_fake_products(1), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(return_value={"saved_count": 1})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",), limit=25), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        crawler.crawl_with_metrics.assert_awaited_once()
        kwargs = crawler.crawl_with_metrics.await_args.kwargs
        assert kwargs["keyword"] == "海苔卷"
        assert kwargs["limit"] == 25

    @pytest.mark.anyio
    async def test_save_called_with_collected_products(self):
        crawl_result = SimpleNamespace(products=_fake_products(2), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(return_value={"saved_count": 2})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        save_mock.assert_awaited_once()
        saved_arg = save_mock.await_args.args[0]
        assert len(saved_arg) == 2

    @pytest.mark.anyio
    async def test_crawler_closed(self):
        crawl_result = SimpleNamespace(products=[], failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", AsyncMock()):
            await taobao_daily_collect(ctx)

        crawler.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_no_products_skips_save(self):
        crawl_result = SimpleNamespace(products=[], failure_reason="no_products_found")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock()

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        save_mock.assert_not_awaited()
        assert ctx.result["total"] == 0
        assert ctx.result["success"] == 0

    @pytest.mark.anyio
    async def test_multi_keyword_aggregation(self):
        crawler = _make_crawler(
            crawl_side_effect=[
                SimpleNamespace(products=_fake_products(2), failure_reason=""),
                SimpleNamespace(products=_fake_products(3), failure_reason=""),
            ]
        )
        save_mock = AsyncMock(return_value={"saved_count": 5})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("A", "B")), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        assert crawler.crawl_with_metrics.await_count == 2
        assert ctx.result["total"] == 5
        assert ctx.result["success"] == 5

    @pytest.mark.anyio
    async def test_partial_save_counts_failed(self):
        crawl_result = SimpleNamespace(products=_fake_products(5), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(return_value={"saved_count": 3})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        assert ctx.result["total"] == 5
        assert ctx.result["success"] == 3
        assert ctx.result["failed"] == 2


# ═══════════════════════════════════════════════════════════════
# 异常处理
# ═══════════════════════════════════════════════════════════════


class TestExceptionHandling:
    """采集/保存异常处理。"""

    @pytest.mark.anyio
    async def test_single_keyword_crawl_failure_is_resilient(self):
        """单关键词采集抛错不应中断整体，任务仍完成。"""
        crawler = _make_crawler(
            crawl_side_effect=[
                RuntimeError("boom"),
                SimpleNamespace(products=_fake_products(2), failure_reason=""),
            ]
        )
        save_mock = AsyncMock(return_value={"saved_count": 2})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("bad", "good")), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        assert ctx.completed is True
        assert ctx.error is None
        assert ctx.result["total"] == 2
        assert ctx.result["success"] == 2
        # 1 个关键词失败被计入 failed
        assert ctx.result["failed"] >= 1
        crawler.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_save_failure_sets_error(self):
        """保存阶段致命异常应通过 ctx.set_error 记录。"""
        crawl_result = SimpleNamespace(products=_fake_products(2), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(side_effect=RuntimeError("db down"))

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        assert ctx.completed is True
        assert ctx.error is not None
        assert "db down" in ctx.error
        assert ctx.result is None
        # 即便失败仍应关闭爬虫
        crawler.close.assert_awaited_once()

    @pytest.mark.anyio
    async def test_close_failure_does_not_break_result(self):
        """close 抛错不应影响已设置的 result。"""
        crawl_result = SimpleNamespace(products=_fake_products(1), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        crawler.close = AsyncMock(side_effect=RuntimeError("close fail"))
        save_mock = AsyncMock(return_value={"saved_count": 1})

        ctx = TaskContext(task_name="taobao_daily_collect")
        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock):
            await taobao_daily_collect(ctx)

        assert ctx.result["success"] == 1


# ═══════════════════════════════════════════════════════════════
# Registry 注册（任务名/触发器保持不变）
# ═══════════════════════════════════════════════════════════════


class TestRegistration:
    def test_task_name_unchanged(self):
        registry = TaskRegistry()
        td = register_taobao_collect_task(registry)
        assert td.name == "taobao_daily_collect"

    def test_trigger_cron_0200(self):
        registry = TaskRegistry()
        td = register_taobao_collect_task(registry)
        assert td.trigger == "cron"
        assert td.trigger_kwargs == {"hour": 2, "minute": 0}

    def test_registered_in_registry(self):
        registry = TaskRegistry()
        register_taobao_collect_task(registry)
        assert registry.get_task("taobao_daily_collect") is not None


# ═══════════════════════════════════════════════════════════════
# Scheduler 同步
# ═══════════════════════════════════════════════════════════════


class TestSchedulerSync:
    def test_sync_success(self):
        from app.scheduler.scheduler import SchedulerManager

        registry = TaskRegistry()
        register_taobao_collect_task(registry)

        mgr = SchedulerManager()
        count = registry.sync_to_scheduler(mgr)
        assert count == 1
        assert mgr.job_count == 1
        job_ids = {j["id"] for j in mgr.get_jobs()}
        assert "taobao_daily_collect" in job_ids


# ═══════════════════════════════════════════════════════════════
# 闭环: 通过注册 func 执行，返回 ctx.to_dict()
# ═══════════════════════════════════════════════════════════════


class TestClosedLoop:
    @pytest.mark.anyio
    async def test_registered_func_returns_context_dict(self):
        crawl_result = SimpleNamespace(products=_fake_products(2), failure_reason="")
        crawler = _make_crawler(crawl_return=crawl_result)
        save_mock = AsyncMock(return_value={"saved_count": 2})

        # 让 TaskExecutionLogger 的 DB 记录成为 no-op（不写真实库）
        logger_execute = AsyncMock()

        async def _fake_execute(name, func, *args, **kwargs):
            return await func(*args, **kwargs)

        logger_execute.side_effect = _fake_execute

        registry = TaskRegistry()
        register_taobao_collect_task(registry)
        td = registry.get_task("taobao_daily_collect")

        with _patch_settings(keywords=("海苔卷",)), patch(
            "app.crawler.taobao.TaobaoCrawler", return_value=crawler
        ), patch(f"{TASK_MODULE}._save_products", save_mock), patch(
            "app.tasks.execution_logger.TaskExecutionLogger.execute", logger_execute
        ):
            result = await td.func()

        assert result["task_name"] == "taobao_daily_collect"
        assert result["completed"] is True
        assert result["result"]["total"] == 2
        assert result["result"]["success"] == 2
