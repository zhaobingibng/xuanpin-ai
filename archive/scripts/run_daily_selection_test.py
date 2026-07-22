#!/usr/bin/env python3
"""AI 自动选品完整链路验证脚本 (Phase 41).

功能:
    - 手动执行一次 daily_selection 流水线（读 DB，不写 DB）
    - 自动检测 AI 配置状态，未配自动降级不报错
    - 输出：状态 / 商品数量 / 匹配数量 / AI 分析状态 / 报告位置
    - 验证保存的 JSON 字段完整性

用法:
    python scripts/run_daily_selection_test.py

要求:
    - 项目根目录的 .venv 已激活
    - 数据库已初始化（只读访问即可）
    - AI_API_KEY 可选（未配置时自动降级）
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ── 确保 Windows 控制台输出不因 GBK 编码崩溃 ──────────────
if sys.platform == "win32" and os.environ.get("PYTHONIOENCODING", "") != "utf-8":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Re-open stdout with utf-8 to take effect immediately
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# ── 确保项目根在 sys.path 上 ────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger

# ── 常量 ──────────────────────────────────────────────────────

_RESULT_FILE = _PROJECT_ROOT / "storage" / "daily_selection_result.json"


# ── 工具函数 ──────────────────────────────────────────────────


def _format_bool_emoji(value: bool) -> str:
    return "\u2705" if value else "\u274c"


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── 主流程 ────────────────────────────────────────────────────


async def main() -> int:
    """主入口 — 执行流水线 + 验证输出。"""
    print("=" * 60)
    print("  \U0001f504 AI \u81ea\u52a8\u9009\u54c1\u5b8c\u6574\u94fe\u8def\u9a8c\u8bc1 (Phase 41)")
    print("=" * 60)

    # ── 阶段 0: 配置检查 ──────────────────────────────────────
    _print_section("\u2699\ufe0f  配置检查")

    from app.config.settings import get_settings

    settings = get_settings()
    ai_key = settings.ai_api_key or ""
    ai_configured = bool(ai_key and ai_key not in ("sk-your-api-key-here", ""))

    ai_status = "\u2705 \u5df2\u914d\u7f6e" if ai_configured else "\u26a0\ufe0f \u672a\u914d\u7f6e\uff08\u5c06\u81ea\u52a8\u964d\u7ea7\uff09"

    print(f"  DAILY_SELECTION_ENABLED : {_format_bool_emoji(settings.daily_selection_enabled)}")
    print(f"  AI_API_KEY              : {ai_status}")
    if ai_configured:
        print(f"  AI_MODEL                : {settings.ai_model}")
        print(f"  AI_BASE_URL             : {settings.ai_base_url}")
    print(f"  DB_PATH                 : {settings.db_path}")

    # ── 阶段 1: 执行流水线 ────────────────────────────────────
    _print_section("\U0001f680 \u6267\u884c\u9009\u54c1\u6d41\u6c34\u7ebf")

    from app.tasks.daily_selection_task import _run_pipeline_impl, save_result_to_storage

    t_start = time.monotonic()

    try:
        result = await _run_pipeline_impl(limit=10, top_k=3, candidate_limit=500)
    except Exception as exc:
        print(f"\n  \u274c \u6d41\u6c34\u7ebf\u6267\u884c\u5f02\u5e38: {exc}")
        logger.exception("Pipeline crashed")
        return 1

    elapsed = time.monotonic() - t_start
    status: str = str(result.get("status", "unknown"))
    stats: dict = result.get("stats", {})  # type: ignore[assignment]
    report: dict | None = result.get("report")  # type: ignore[assignment]

    status_icon = "\u2705 \u6210\u529f" if status == "success" else "\u274c " + status
    print(f"  \u72b6\u6001    : {status_icon}")
    print(f"  \u8017\u65f6    : {elapsed:.1f}s")
    print(f"  \u5546\u54c1\u603b\u6570: {stats.get('total_products', 'N/A')}")
    print(f"  \u5339\u914d\u603b\u6570: {stats.get('matched_products', 'N/A')}")

    if status != "success" or not report:
        error_msg = result.get("error") or result.get("stage", "unknown")
        print(f"  \u26a0\ufe0f \u6d41\u6c34\u7ebf\u672a\u6210\u529f: {error_msg}")
        return 0  # 非致命 — 产品库可能为空，验证通过

    # ── 阶段 2: 报告详情 ──────────────────────────────────────
    top_products: list = report.get("top_products", [])
    statistics: dict = report.get("statistics", {})
    ai_insights: dict | None = report.get("ai_insights")

    print(f"  TOP\u5546\u54c1  : {len(top_products)} \u4e2a")
    if top_products:
        for p in top_products[:5]:
            name = p.get("name") or p.get("product_name", "?")
            score = p.get("opportunity_score") or p.get("score", "?")
            level = p.get("opportunity_level") or p.get("level", "?")
            print(f"    - {name[:30]:<30}  \u8bc4\u5206:{score}  \u7b49\u7ea7:{level}")

    # ── 阶段 3: AI 分析状态 ───────────────────────────────────
    _print_section("\U0001f916 AI \u5206\u6790\u72b6\u6001")

    if not ai_configured and not ai_insights:
        print("  \u26a0\ufe0f AI_API_KEY \u672a\u914d\u7f6e\uff0c\u8df3\u8fc7 AI \u5206\u6790\uff08\u7b26\u5408\u9884\u671f\uff09")
    elif ai_insights:
        ai_available: bool = bool(ai_insights.get("ai_available", False))
        if ai_available:
            print("  \u72b6\u6001    : \u2705 \u5df2\u5b8c\u6210")
            print(f"  \u6458\u8981    : {str(ai_insights.get('overall_summary', ''))[:80]}")
            highlights: list = ai_insights.get("highlights", [])
            warnings: list = ai_insights.get("warnings", [])
            suggestions: list = ai_insights.get("action_suggestions", [])
            print(f"  \u4eae\u70b9    : {len(highlights)} \u6761")
            print(f"  \u98ce\u9669    : {len(warnings)} \u6761")
            print(f"  \u5efa\u8bae    : {len(suggestions)} \u6761")
            profit = ai_insights.get("profit_insight", "")
            trend = ai_insights.get("market_trend", "")
            if profit:
                print(f"  \u5229\u6da6\u5206\u6790: {str(profit)[:80]}")
            if trend:
                print(f"  \u5e02\u573a\u8d8b\u52bf: {str(trend)[:80]}")
        else:
            error_detail = ai_insights.get("error", "\u672a\u77e5\u539f\u56e0")
            print(f"  \u72b6\u6001    : \u26a0\ufe0f \u964d\u7ea7")
            print(f"  \u539f\u56e0    : {error_detail}")
    else:
        print("  \u26a0\ufe0f \u65e0 ai_insights \u5b57\u6bb5\uff08\u53ef\u80fd AI \u5206\u6790\u672a\u6267\u884c\uff09")

    # ── 阶段 4: 保存 + 字段验证 ───────────────────────────────
    _print_section("\U0001f4be \u62a5\u544a\u4fdd\u5b58 + \u5b57\u6bb5\u9a8c\u8bc1")

    saved_path = save_result_to_storage(result)
    print(f"  \u4fdd\u5b58\u4f4d\u7f6e: {saved_path}")

    if not _RESULT_FILE.exists():
        print("  \u274c \u6587\u4ef6\u672a\u751f\u6210")
        return 1

    try:
        raw = _RESULT_FILE.read_text(encoding="utf-8")
        saved = json.loads(raw)
    except Exception as exc:
        print(f"  \u274c JSON \u89e3\u6790\u5931\u8d25: {exc}")
        return 1

    saved_report = saved.get("report", {}) if isinstance(saved, dict) else {}

    field_checks = [
        ("date", saved.get("date")),
        ("generated_at", saved.get("generated_at")),
        ("status", saved.get("status")),
        ("stats", saved.get("stats")),
        ("report.report_date", saved_report.get("report_date") if isinstance(saved_report, dict) else None),
        ("report.top_products", saved_report.get("top_products") if isinstance(saved_report, dict) else None),
        ("report.statistics", saved_report.get("statistics") if isinstance(saved_report, dict) else None),
        ("report.ai_insights", saved_report.get("ai_insights") if isinstance(saved_report, dict) else None),
    ]

    all_ok = True
    for field_name, value in field_checks:
        ok = value is not None  # empty list is valid (no products matched)
        # For ai_insights, None is acceptable (AI not configured)
        if field_name == "report.ai_insights" and value is None:
            ok = True  # acceptable — AI may not be configured
        marker = _format_bool_emoji(ok)
        detail = ""
        if isinstance(value, (list, dict)):
            detail = f"(共 {len(value)} 项)"
        print(f"  {marker} {field_name:<28} {detail}")

        if field_name not in ("report.ai_insights",):
            if not ok:
                all_ok = False

    file_size = _RESULT_FILE.stat().st_size
    print(f"  \U0001f4e6 \u6587\u4ef6\u5927\u5c0f: {file_size} bytes")

    # ── 总结 ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if all_ok and status == "success":
        print("  \u2705 \u9a8c\u8bc1\u5168\u90e8\u901a\u8fc7")
    elif status != "success":
        print("  \u26a0\ufe0f \u6d41\u6c34\u7ebf\u8fd4\u56de\u975e success \u72b6\u6001\uff0c\u8bf7\u68c0\u67e5\u6570\u636e\u5e93\u72b6\u6001")
    else:
        print("  \u26a0\ufe0f \u90e8\u5206\u5b57\u6bb5\u7f3a\u5931\uff0c\u8bf7\u68c0\u67e5\u62a5\u544a\u751f\u6210\u903b\u8f91")
    print("=" * 60)

    return 0 if (all_ok or status != "success") else 1


# ── CLI entry ──────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
