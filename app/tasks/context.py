"""TaskContext — unified runtime context for business tasks (Phase 44.4.0).

Provides a standard interface for tasks to:
- Access task name / execution_id
- Record results and errors
- Attach runtime metadata
- Emit structured log messages

Designed to integrate with TaskExecutionLogger without modifying it:
    logger = TaskExecutionLogger()
    ctx = TaskContext(task_name="daily_crawl", execution_id=record_id)
    await task_func(ctx)          # task reads/writes ctx
    # logger uses ctx.execution_id to update the DB record

Usage::

    async def my_task(ctx: TaskContext) -> None:
        ctx.log("Starting processing")
        ctx.add_metadata("source", "taobao")
        ...
        ctx.set_result({"count": 42})
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from loguru import logger as loguru_logger


class TaskContext:
    """任务运行上下文。

    封装单次任务执行的全部运行时状态：
    - 基础信息：task_name, execution_id, started_at
    - 运行结果：result, error
    - 自定义元数据：metadata (add_metadata / get_metadata)
    - 格式化日志：log()

    Attributes:
        task_name: 任务名称。
        execution_id: 数据库 TaskExecution 记录 ID（可选）。
        started_at: 上下文创建时间（UTC）。
        completed: 是否已完成（set_result / set_error 后为 True）。
    """

    __slots__ = (
        "task_name",
        "execution_id",
        "started_at",
        "_result",
        "_error",
        "_metadata",
        "_completed",
    )

    def __init__(
        self,
        task_name: str,
        execution_id: int | None = None,
        *,
        started_at: datetime | None = None,
    ) -> None:
        """创建任务上下文。

        Args:
            task_name: 任务名称，用于日志前缀。
            execution_id: 关联的 TaskExecution 数据库记录 ID。
            started_at: 启动时间，默认当前 UTC 时间。
        """
        self.task_name = task_name
        self.execution_id = execution_id
        self.started_at = started_at or datetime.now(timezone.utc)

        self._result: dict[str, Any] | None = None
        self._error: str | None = None
        self._metadata: dict[str, Any] = {}
        self._completed = False

    # ── Result & error ─────────────────────────────────────────

    def set_result(self, result: dict[str, Any]) -> None:
        """设置任务执行结果。

        Args:
            result: 结构化结果字典。
        """
        self._result = result
        self._completed = True
        self.log("Task completed with result")

    def set_error(self, error: Exception | str) -> None:
        """记录任务错误。

        Args:
            error: 异常对象或错误描述字符串。
        """
        if isinstance(error, Exception):
            self._error = f"{type(error).__name__}: {error}"
        else:
            self._error = error
        self._completed = True
        self.log(f"Task failed: {self._error}")

    # ── Metadata ───────────────────────────────────────────────

    def add_metadata(self, key: str, value: Any) -> None:
        """增加运行元数据。

        用于记录与任务运行环境相关的信息（如平台、参数、版本等）。

        Args:
            key: 元数据键。
            value: 元数据值。
        """
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """读取指定元数据。

        Args:
            key: 元数据键。
            default: 键不存在时的默认返回值。

        Returns:
            元数据值，或 default。
        """
        return self._metadata.get(key, default)

    # ── Properties ─────────────────────────────────────────────

    @property
    def result(self) -> dict[str, Any] | None:
        """任务执行结果（set_result 设置的）。"""
        return self._result

    @property
    def error(self) -> str | None:
        """错误信息（set_error 设置的）。"""
        return self._error

    @property
    def completed(self) -> bool:
        """任务是否已完成（调用了 set_result 或 set_error）。"""
        return self._completed

    @property
    def metadata(self) -> dict[str, Any]:
        """运行时元数据（只读副本）。"""
        return dict(self._metadata)

    # ── Logging ────────────────────────────────────────────────

    def log(self, message: str, level: str = "INFO") -> None:
        """输出带任务上下文的格式化日志。

        日志格式: [task_name][#execution_id] message

        Args:
            message: 日志消息内容。
            level: 日志级别（DEBUG/INFO/WARNING/ERROR），默认 INFO。
        """
        prefix = f"[{self.task_name}]"
        if self.execution_id is not None:
            prefix += f"[#{self.execution_id}]"

        full_msg = f"{prefix} {message}"

        log_method = getattr(loguru_logger, level.lower(), loguru_logger.info)
        log_method(full_msg)

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """输出完整上下文信息。

        Returns:
            包含所有字段的结构化字典::

                {
                    "task_name": str,
                    "execution_id": int | None,
                    "started_at": "ISO-8601 str",
                    "completed": bool,
                    "result": dict | None,
                    "error": str | None,
                    "metadata": dict,
                }
        """
        return {
            "task_name": self.task_name,
            "execution_id": self.execution_id,
            "started_at": self.started_at.isoformat(),
            "completed": self._completed,
            "result": self._result,
            "error": self._error,
            "metadata": dict(self._metadata),
        }

    def __repr__(self) -> str:
        eid = f"#{self.execution_id}" if self.execution_id is not None else "?"
        return f"<TaskContext({self.task_name}, id={eid}, completed={self._completed})>"
