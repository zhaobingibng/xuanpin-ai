"""Tests for Phase 44.4.0 — TaskContext unified runtime context.

Covers:
- 初始化 (task_name / execution_id / started_at / metadata 默认值)
- metadata 操作 (add_metadata / get_metadata / metadata 只读副本)
- result 设置 (set_result)
- error 设置 (set_error, Exception 与 str)
- to_dict 结构
- log 输出 (格式 [task_name][#execution_id] message)
- execution_id 关联
- completed 标记
- __repr__
- 与任务函数集成模式 (async def task(ctx: TaskContext))
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.tasks.context import TaskContext


# ── 初始化 ──────────────────────────────────────────────────────


class TestInit:
    def test_basic_init(self):
        ctx = TaskContext("my_task")
        assert ctx.task_name == "my_task"

    def test_execution_id_defaults_none(self):
        ctx = TaskContext("my_task")
        assert ctx.execution_id is None

    def test_execution_id_set(self):
        ctx = TaskContext("my_task", execution_id=42)
        assert ctx.execution_id == 42

    def test_started_at_is_datetime(self):
        ctx = TaskContext("my_task")
        assert isinstance(ctx.started_at, datetime)

    def test_started_at_is_utc(self):
        ctx = TaskContext("my_task")
        assert ctx.started_at.tzinfo is not None

    def test_started_at_override(self):
        fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ctx = TaskContext("my_task", started_at=fixed)
        assert ctx.started_at == fixed

    def test_result_defaults_none(self):
        ctx = TaskContext("my_task")
        assert ctx.result is None

    def test_error_defaults_none(self):
        ctx = TaskContext("my_task")
        assert ctx.error is None

    def test_completed_defaults_false(self):
        ctx = TaskContext("my_task")
        assert ctx.completed is False

    def test_metadata_defaults_empty(self):
        ctx = TaskContext("my_task")
        assert ctx.metadata == {}


# ── set_result ─────────────────────────────────────────────────


class TestSetResult:
    def test_set_result_stores(self):
        ctx = TaskContext("my_task")
        ctx.set_result({"count": 3})
        assert ctx.result == {"count": 3}

    def test_set_result_marks_completed(self):
        ctx = TaskContext("my_task")
        ctx.set_result({"count": 3})
        assert ctx.completed is True

    def test_set_result_no_error(self):
        ctx = TaskContext("my_task")
        ctx.set_result({"count": 3})
        assert ctx.error is None


# ── set_error ──────────────────────────────────────────────────


class TestSetError:
    def test_set_error_with_string(self):
        ctx = TaskContext("my_task")
        ctx.set_error("something failed")
        assert ctx.error == "something failed"

    def test_set_error_with_exception(self):
        ctx = TaskContext("my_task")
        ctx.set_error(ValueError("bad value"))
        assert ctx.error == "ValueError: bad value"

    def test_set_error_marks_completed(self):
        ctx = TaskContext("my_task")
        ctx.set_error("boom")
        assert ctx.completed is True

    def test_set_error_keeps_result_none(self):
        ctx = TaskContext("my_task")
        ctx.set_error("boom")
        assert ctx.result is None


# ── metadata ───────────────────────────────────────────────────


class TestMetadata:
    def test_add_metadata(self):
        ctx = TaskContext("my_task")
        ctx.add_metadata("source", "taobao")
        assert ctx.get_metadata("source") == "taobao"

    def test_add_metadata_multiple(self):
        ctx = TaskContext("my_task")
        ctx.add_metadata("a", 1)
        ctx.add_metadata("b", 2)
        assert ctx.get_metadata("a") == 1
        assert ctx.get_metadata("b") == 2

    def test_add_metadata_overwrite(self):
        ctx = TaskContext("my_task")
        ctx.add_metadata("k", 1)
        ctx.add_metadata("k", 2)
        assert ctx.get_metadata("k") == 2

    def test_get_metadata_default(self):
        ctx = TaskContext("my_task")
        assert ctx.get_metadata("missing", "fallback") == "fallback"

    def test_get_metadata_missing_none(self):
        ctx = TaskContext("my_task")
        assert ctx.get_metadata("missing") is None

    def test_metadata_property_is_copy(self):
        ctx = TaskContext("my_task")
        ctx.add_metadata("k", 1)
        snapshot = ctx.metadata
        snapshot["k"] = 999
        assert ctx.get_metadata("k") == 1


# ── to_dict ────────────────────────────────────────────────────


class TestToDict:
    def test_to_dict_keys(self):
        ctx = TaskContext("my_task", execution_id=7)
        d = ctx.to_dict()
        assert set(d.keys()) == {
            "task_name",
            "execution_id",
            "started_at",
            "completed",
            "result",
            "error",
            "metadata",
        }

    def test_to_dict_values(self):
        ctx = TaskContext("my_task", execution_id=7)
        ctx.add_metadata("source", "taobao")
        ctx.set_result({"count": 5})
        d = ctx.to_dict()
        assert d["task_name"] == "my_task"
        assert d["execution_id"] == 7
        assert d["completed"] is True
        assert d["result"] == {"count": 5}
        assert d["error"] is None
        assert d["metadata"] == {"source": "taobao"}

    def test_to_dict_started_at_is_iso_string(self):
        ctx = TaskContext("my_task")
        d = ctx.to_dict()
        assert isinstance(d["started_at"], str)
        # round-trip parse should not raise
        datetime.fromisoformat(d["started_at"])

    def test_to_dict_metadata_is_copy(self):
        ctx = TaskContext("my_task")
        ctx.add_metadata("k", 1)
        d = ctx.to_dict()
        d["metadata"]["k"] = 999
        assert ctx.get_metadata("k") == 1

    def test_to_dict_error_state(self):
        ctx = TaskContext("my_task")
        ctx.set_error(RuntimeError("boom"))
        d = ctx.to_dict()
        assert d["error"] == "RuntimeError: boom"
        assert d["result"] is None
        assert d["completed"] is True


# ── log ────────────────────────────────────────────────────────


class TestLog:
    def test_log_prefix_with_execution_id(self):
        ctx = TaskContext("crawl", execution_id=12)
        with patch("app.tasks.context.loguru_logger.info") as mock_info:
            ctx.log("hello")
        mock_info.assert_called_once_with("[crawl][#12] hello")

    def test_log_prefix_without_execution_id(self):
        ctx = TaskContext("crawl")
        with patch("app.tasks.context.loguru_logger.info") as mock_info:
            ctx.log("hello")
        mock_info.assert_called_once_with("[crawl] hello")

    def test_log_respects_level(self):
        ctx = TaskContext("crawl", execution_id=1)
        with patch("app.tasks.context.loguru_logger.warning") as mock_warn:
            ctx.log("careful", level="WARNING")
        mock_warn.assert_called_once_with("[crawl][#1] careful")

    def test_log_unknown_level_falls_back_to_info(self):
        ctx = TaskContext("crawl")
        with patch("app.tasks.context.loguru_logger.info") as mock_info:
            ctx.log("msg", level="NONEXISTENT")
        mock_info.assert_called_once_with("[crawl] msg")

    def test_set_result_emits_log(self):
        ctx = TaskContext("crawl", execution_id=3)
        with patch("app.tasks.context.loguru_logger.info") as mock_info:
            ctx.set_result({"x": 1})
        mock_info.assert_called_once()
        assert "[crawl][#3]" in mock_info.call_args[0][0]

    def test_set_error_emits_log(self):
        ctx = TaskContext("crawl", execution_id=3)
        with patch("app.tasks.context.loguru_logger.info") as mock_info:
            ctx.set_error("boom")
        mock_info.assert_called_once()
        assert "boom" in mock_info.call_args[0][0]


# ── completed 标记 ───────────────────────────────────────────────


class TestCompletedFlag:
    def test_not_completed_initially(self):
        ctx = TaskContext("t")
        assert ctx.completed is False

    def test_completed_after_result(self):
        ctx = TaskContext("t")
        ctx.set_result({})
        assert ctx.completed is True


# ── __repr__ ───────────────────────────────────────────────────


class TestRepr:
    def test_repr_contains_task_name(self):
        ctx = TaskContext("my_task", execution_id=5)
        assert "my_task" in repr(ctx)

    def test_repr_contains_execution_id(self):
        ctx = TaskContext("my_task", execution_id=5)
        assert "#5" in repr(ctx)

    def test_repr_without_execution_id(self):
        ctx = TaskContext("my_task")
        assert "?" in repr(ctx)

    def test_repr_shows_completed(self):
        ctx = TaskContext("my_task")
        ctx.set_result({})
        assert "completed=True" in repr(ctx)


# ── 与任务函数集成模式 ─────────────────────────────────────────────


class TestIntegrationPattern:
    @pytest.mark.anyio
    async def test_context_passed_to_task_function(self):
        async def sample_task(ctx: TaskContext) -> None:
            ctx.log("task started")
            ctx.add_metadata("provider", "mock")
            ctx.set_result({"items": 5})

        ctx = TaskContext("sample_task", execution_id=99)
        await sample_task(ctx)

        assert ctx.completed is True
        assert ctx.result == {"items": 5}
        assert ctx.get_metadata("provider") == "mock"

    @pytest.mark.anyio
    async def test_task_error_captured_in_context(self):
        async def failing_task(ctx: TaskContext) -> None:
            try:
                raise ValueError("bad")
            except ValueError as exc:
                ctx.set_error(exc)

        ctx = TaskContext("failing_task", execution_id=100)
        await failing_task(ctx)

        assert ctx.completed is True
        assert ctx.error == "ValueError: bad"
        assert ctx.result is None

    @pytest.mark.anyio
    async def test_execution_id_links_to_task_execution_record(self):
        # execution_id 对应 TaskExecution.id，用于关联数据库记录
        record_id = 12345
        ctx = TaskContext("linked_task", execution_id=record_id)
        assert ctx.to_dict()["execution_id"] == record_id
