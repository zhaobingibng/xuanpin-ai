"""Unified exception hierarchy — 保持简单。

原则（遵守项目宪法 Article X）：
- 只保留真正需要的异常
- 不无限细分
- 用 code 字符串区分场景，不用类层次

当前：
- BaseAppException — 根异常，所有应用异常基类
- PublishException — 发布流程异常
- RecommendationException — 推荐/评分/池评估异常

Usage::

    from app.core.exceptions import PublishException

    raise PublishException(
        code="NOT_APPROVED",
        message="商品未通过审核，无法发布",
        details={"product_id": 42, "status": "NEW"},
    )
"""

from __future__ import annotations

from typing import Any


class BaseAppException(Exception):
    """应用异常根类。

    Attributes:
        code: 机器可读错误码（如 "NOT_FOUND", "NOT_APPROVED"）。
        message: 人类可读错误描述。
        details: 调试用额外上下文。
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ── Business Domain Exceptions ──────────────────────────────────

# 故意同时继承 ValueError，兼容现有 ``except ValueError`` 路由。


class PublishException(BaseAppException, ValueError):
    """发布流程异常（未审核、平台不支持等）。"""


class RecommendationException(BaseAppException, ValueError):
    """推荐/评分/池评估异常。"""
