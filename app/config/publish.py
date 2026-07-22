"""Publish module settings — 发布相关配置 (Phase 47.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishSettings:
    """发布模块配置。"""

    # MockPublisher 模拟成功率 (0.0 ~ 1.0)
    success_rate: float = 0.85


# 模块级单例
publish_settings = PublishSettings()
