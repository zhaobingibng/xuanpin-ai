"""Crawler module settings — 爬虫行为配置 (Phase 47.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrawlerSettings:
    """爬虫行为配置（反爬延迟、页面等待等）。"""

    # ── 反爬随机延迟 (ms) ────────────────────────────────
    random_delay_min_ms: int = 500
    random_delay_max_ms: int = 2000

    # ── 随机滚动 ──────────────────────────────────────────
    scroll_times: int = 3
    scroll_distance_min: int = 300
    scroll_distance_max: int = 800
    scroll_sleep_min_s: float = 0.3
    scroll_sleep_max_s: float = 1.0

    # ── 鼠标模拟 ──────────────────────────────────────────
    mouse_move_x_min: int = 100
    mouse_move_x_max: int = 350
    mouse_move_y_min: int = 200
    mouse_move_y_max: int = 700
    mouse_move_sleep_min_s: float = 0.1
    mouse_move_sleep_max_s: float = 0.5

    # ── 页面等待 (ms) ────────────────────────────────────
    post_goto_wait_ms: int = 2000
    """页面导航后等待时间。"""
    post_search_wait_ms: int = 3000
    """搜索后等待时间。"""
    scroll_wait_ms: int = 500
    """滚动间隔等待时间。"""

    # ── 滚动加载 ──────────────────────────────────────────
    scroll_loop_count: int = 10
    """小红书/1688 无限滚动加载循环次数。"""

    # ── 反爬探测 ──────────────────────────────────────────
    anti_bot_probe_timeout_ms: int = 15000
    """反爬探测页面超时（如小红书 300012 检测）。"""


# 模块级单例
crawler_settings = CrawlerSettings()
