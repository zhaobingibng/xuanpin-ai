"""Admin API — 后台管理接口（纯编排层，不写业务逻辑）。

Phase 43.1: 最大化复用已有 Service，零新增 Service。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.database.base import get_async_session_factory

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Request models ───────────────────────────────────────────

class FeishuSendRequest(BaseModel):
    content: str
    msg_type: str = "text"


# ═══════════════════════════════════════════════════════════════
# 1. 系统状态总览
# ═══════════════════════════════════════════════════════════════


@router.get("/status")
async def admin_status() -> dict[str, Any]:
    """返回系统综合状态：登录态 + DB + Scheduler。

    聚合 HealthService / LoginHelper / TaobaoSessionService 的结果。
    """
    result: dict[str, Any] = {"success": True, "data": {}}

    # ── DB + Scheduler 状态 ──────────────────────────────────
    try:
        from app.api.main import _scheduler_instance
        from app.services.health.service import HealthService

        scheduler_running = (
            _scheduler_instance is not None and _scheduler_instance.running
        )
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            health_svc = HealthService(session, scheduler_running=scheduler_running)
            health = await health_svc.check()
            result["data"]["health"] = health
    except Exception as e:
        logger.warning("[Admin] health check failed: {}", e)
        result["data"]["health"] = {"status": "error", "error": str(e)}

    # ── 登录状态 ──────────────────────────────────────────────
    try:
        from app.services.login_helper import LoginHelper

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            login_helper = LoginHelper(session)
            login_summary = await login_helper.get_login_status_summary()
            result["data"]["login"] = login_summary
    except Exception as e:
        logger.warning("[Admin] login status check failed: {}", e)
        result["data"]["login"] = {"error": str(e)}

    # ── 淘宝浏览器会话 ───────────────────────────────────────
    try:
        from app.services.taobao_session_service import get_taobao_session

        taobao_svc = get_taobao_session()
        info = taobao_svc.get_snapshot()
        result["data"]["taobao_session"] = {
            "state": info.state.value,
            "is_logged_in": info.is_logged_in,
            "is_blocked": info.is_blocked,
            "block_reason": info.block_reason,
            "message": info.message,
        }
    except Exception as e:
        logger.warning("[Admin] taobao session check failed: {}", e)
        result["data"]["taobao_session"] = {"error": str(e)}

    return result


# ═══════════════════════════════════════════════════════════════
# 2. 淘宝登录/会话状态
# ═══════════════════════════════════════════════════════════════


@router.get("/taobao/status")
async def admin_taobao_status() -> dict[str, Any]:
    """淘宝登录状态：LoginHelper（文件+DB）+ TaobaoSessionService（浏览器会话）。"""
    result: dict[str, Any] = {"success": True, "data": {}}

    # ── LoginHelper（state file + DB session）──────────────────
    try:
        from app.services.login_helper import LoginHelper

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            login_helper = LoginHelper(session)
            summary = await login_helper.get_login_status_summary()
            result["data"]["login"] = summary.get("taobao", {})
    except Exception as e:
        logger.warning("[Admin] LoginHelper failed: {}", e)
        result["data"]["login"] = {"error": str(e)}

    # ── TaobaoSessionService（浏览器会话）─────────────────────
    try:
        from app.services.taobao_session_service import get_taobao_session

        taobao_svc = get_taobao_session()
        info = taobao_svc.get_snapshot()

        # 附带商品总数
        product_count = 0
        try:
            async_session_factory = get_async_session_factory()
            async with async_session_factory() as session:
                from sqlalchemy import text
                row = await session.execute(
                    text("SELECT COUNT(*) FROM products WHERE platform = 'taobao'")
                )
                count = row.scalar()
                product_count = count if isinstance(count, (int, float)) else 0
        except Exception:
            pass

        result["data"]["session"] = {
            "state": info.state.value,
            "is_logged_in": info.is_logged_in,
            "is_blocked": info.is_blocked,
            "block_reason": info.block_reason,
            "last_check": info.last_check.isoformat() if info.last_check else None,
            "last_crawl": info.last_crawl.isoformat() if info.last_crawl else None,
            "last_crawl_keyword": info.last_crawl_keyword,
            "last_crawl_count": info.last_crawl_count,
            "session_started": info.session_started.isoformat() if info.session_started else None,
            "message": info.message,
            "product_count": product_count,
        }
    except Exception as e:
        logger.warning("[Admin] TaobaoSessionService failed: {}", e)
        result["data"]["session"] = {"error": str(e)}

    return result


# ═══════════════════════════════════════════════════════════════
# 3. 今日推荐
# ═══════════════════════════════════════════════════════════════


@router.get("/recommendations")
async def admin_recommendations() -> dict[str, Any]:
    """获取今日推荐结果。

    调用 DailyRecommendationService.generate()。
    """
    try:
        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyRecommendationService(session)
            report = await svc.generate()

            return {
                "success": True,
                "data": {
                    "date": report["date"],
                    "total": report["total"],
                    "items": report["items"][:20],
                },
                "message": f"共 {report['total']} 条推荐",
            }
    except Exception as e:
        logger.error("[Admin] recommendations failed: {}", e)
        raise HTTPException(status_code=500, detail=f"获取推荐失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 4. 最新日报
# ═══════════════════════════════════════════════════════════════


@router.get("/reports/latest")
async def admin_latest_report() -> dict[str, Any]:
    """获取最新一期选品日报。

    调用 ReportRepository.get_history(limit=1)。
    """
    try:
        from app.database.report_repository import ReportRepository

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = ReportRepository(session)
            reports = await repo.get_history(limit=1)

            if not reports:
                return {
                    "success": True,
                    "data": None,
                    "message": "暂无日报",
                }

            r = reports[0]
            return {
                "success": True,
                "data": {
                    "id": r.id,
                    "report_date": r.report_date.isoformat(),
                    "total": r.total,
                    "hot_products": r.hot_products,
                    "potential_products": r.potential_products,
                    "average_score": r.average_score,
                },
                "message": "ok",
            }
    except Exception as e:
        logger.error("[Admin] latest report failed: {}", e)
        raise HTTPException(status_code=500, detail=f"获取最新日报失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 5. 启动淘宝人工采集（非阻塞）
# ═══════════════════════════════════════════════════════════════


@router.post("/taobao/start")
async def admin_taobao_start() -> dict[str, Any]:
    """启动淘宝人工采集会话。

    不阻塞 HTTP — 后台启动浏览器，立即返回 waiting 状态。
    人工采集流程由 TaobaoSessionService 管理，不在此重新实现。
    """
    try:
        from app.services.taobao_session_service import get_taobao_session

        svc = get_taobao_session()

        # 检查当前状态
        snapshot = svc.get_snapshot()
        if snapshot.state.value not in ("idle", "error", "stopping"):
            return {
                "success": True,
                "data": {
                    "state": snapshot.state.value,
                    "is_logged_in": snapshot.is_logged_in,
                    "message": snapshot.message or f"会话已在 {snapshot.state.value} 状态",
                },
                "message": "会话已存在，无需重复启动",
            }

        # 后台启动（真正的浏览器启动由 start_session 处理）
        # start_session 本身是 async 的，但可能较慢（启动浏览器）
        # 使用 create_task 不阻塞 HTTP 响应
        async def _launch() -> None:
            try:
                await svc.start_session()
            except Exception as e:
                logger.error("[Admin] background session launch failed: {}", e)

        asyncio.create_task(_launch())

        return {
            "success": True,
            "data": {
                "state": "starting",
                "is_logged_in": False,
                "message": "浏览器正在后台启动，请稍后查看状态",
            },
            "message": "已触发浏览器启动，请通过 /api/admin/taobao/status 查看进度",
        }
    except Exception as e:
        logger.error("[Admin] taobao start failed: {}", e)
        raise HTTPException(status_code=500, detail=f"启动淘宝采集失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 6. 执行供应链匹配
# ═══════════════════════════════════════════════════════════════


@router.post("/matching/run")
async def admin_matching_run() -> dict[str, Any]:
    """对最近商品批量执行供应链匹配。

    调用 SupplierMatchingService.match_products_with_matcher()。
    为减少耗时，限制处理前 20 条商品。
    """
    try:
        from app.services.product_service import ProductService
        from app.services.supplier_matching import SupplierMatchingService

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            product_svc = ProductService(session)
            products = await product_svc.list_all(limit=20)

            if not products:
                return {
                    "success": True,
                    "data": {"matched": 0, "total": 0},
                    "message": "无商品可供匹配",
                }

            matching_svc = SupplierMatchingService()
            matched = 0
            failed = 0

            for product in products:
                try:
                    matches = await matching_svc.match_products_with_matcher(
                        session, product, top_k=3
                    )
                    if matches:
                        matched += 1
                except Exception as e:
                    logger.warning(
                        "[Admin] matching failed for product {}: {}", product.id, e
                    )
                    failed += 1

            return {
                "success": True,
                "data": {
                    "matched": matched,
                    "failed": failed,
                    "total": len(products),
                },
                "message": f"处理 {len(products)} 条商品，成功匹配 {matched} 条，失败 {failed} 条",
            }
    except Exception as e:
        logger.error("[Admin] matching run failed: {}", e)
        raise HTTPException(status_code=500, detail=f"供应链匹配失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 7. 生成选品报告
# ═══════════════════════════════════════════════════════════════


@router.post("/report/generate")
async def admin_report_generate() -> dict[str, Any]:
    """手动触发每日选品报告生成。

    调用 DailyReportService.generate_and_save()。
    """
    try:
        from app.services.report.daily_report import DailyReportService

        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            svc = DailyReportService(session)
            report = await svc.generate_and_save(limit=20)

            return {
                "success": True,
                "data": {
                    "date": report["date"],
                    "total": report["total"],
                    "hot_products": report["hot_products"],
                    "potential_products": report["potential_products"],
                    "average_score": report["average_score"],
                },
                "message": f"日报已生成：{report['date']}，共 {report['total']} 条",
            }
    except Exception as e:
        logger.error("[Admin] report generate failed: {}", e)
        raise HTTPException(status_code=500, detail=f"生成报告失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 8. 飞书通知
# ═══════════════════════════════════════════════════════════════


@router.post("/feishu/send")
async def admin_feishu_send(req: FeishuSendRequest) -> dict[str, Any]:
    """发送飞书消息通知。

    不硬编码 Webhook — 由 FeishuNotificationService 从 config/feishu.json
    或环境变量 FEISHU_WEBHOOK_URL / FEISHU_SECRET 读取配置。
    未配置时返回未配置状态。
    """
    try:
        from app.services.feishu_notification import FeishuNotificationService

        svc = FeishuNotificationService()

        if not svc.is_enabled:
            return {
                "success": False,
                "data": None,
                "message": "飞书通知未配置。请设置 config/feishu.json 或环境变量 FEISHU_WEBHOOK_URL",
            }

        result = await svc.send_message(req.content, msg_type=req.msg_type)
        return {
            "success": result.get("success", False),
            "data": None,
            "message": result.get("message", ""),
        }
    except Exception as e:
        logger.error("[Admin] feishu send failed: {}", e)
        raise HTTPException(status_code=500, detail=f"飞书发送失败: {e}")
