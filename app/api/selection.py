"""Selection API — cached daily selection report from storage.

Read-only endpoint that serves the latest DailySelectionPipeline result
saved by the scheduler. Never triggers crawler/LLM work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

router = APIRouter(prefix="/api/selection", tags=["selection"])

_RESULT_FILE = Path(__file__).resolve().parent.parent.parent / "storage" / "daily_selection_result.json"


@router.get("/daily")
async def daily_selection_report() -> dict[str, Any]:
    """获取最新每日选品报告（含 AI 分析）。

    从 ``storage/daily_selection_result.json`` 读取由 Scheduler
    定时生成的缓存结果。**不触发任何实时爬虫或 LLM 调用**。

    Returns:
        {
            "date": "2026-07-21",
            "generated_at": "2026-07-21T08:30:00",
            "status": "success",
            "stats": { "total_products": N, "matched_products": N, ... },
            "report": {
                "top_products": [...],
                "statistics": {...},
                "summary": "...",
                "ai_insights": { "ai_available": true, ... }
            }
        }

    Raises:
        HTTPException 404: 尚未生成报告（文件不存在）。
        HTTPException 500: 文件读取/解析异常。
    """
    if not _RESULT_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="选品报告尚未生成。请等待定时任务执行或手动触发 daily_selection_job。",
        )

    try:
        raw = _RESULT_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("[selection-api] 读取缓存报告失败: {}", e)
        raise HTTPException(status_code=500, detail=f"读取选品报告失败: {e}")

    logger.info(
        "[selection-api] 返回缓存报告: date={}, status={}, products={}",
        data.get("date"), data.get("status"),
        data.get("stats", {}).get("total_products", 0),
    )
    return data
