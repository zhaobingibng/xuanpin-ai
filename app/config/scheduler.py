"""Scheduler module settings — 定时任务调度配置 (Phase 47.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerSettings:
    """定时任务调度配置。"""

    # ── 调度时间 ──────────────────────────────────────────
    # 淘宝每日采集
    taobao_collect_hour: int = 2
    taobao_collect_minute: int = 0

    # 1688 供应链匹配
    supplier_matching_hour: int = 4
    supplier_matching_minute: int = 0

    # 每日推荐生成
    daily_recommendation_hour: int = 6
    daily_recommendation_minute: int = 0

    # ── 任务参数 ──────────────────────────────────────────
    # 1688 匹配 TOP-K
    matching_top_k: int = 3

    # 淘宝采集每关键词页数
    taobao_max_pages: int = 1

    # 全平台采集默认页数
    crawl_max_pages: int = 3


# 模块级单例
scheduler_settings = SchedulerSettings()
