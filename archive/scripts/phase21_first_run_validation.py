#!/usr/bin/env python3
"""Phase 21 Task 1: First Production Run Validation.

验证完整生产流程的稳定性：
1. 执行 startup health check
2. 手动触发 daily_selection_task
3. 保存运行报告

Usage:
    python scripts/phase21_first_run_validation.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select

from app.database.base import get_async_session_factory
from app.services.health_check import HealthCheckService
from app.tasks.daily_selection_task import run_daily_selection
from app.models.opportunity_score import OpportunityScore
from app.models.product import Product


async def run_health_check(session) -> dict[str, Any]:
    """Run startup health check.

    Args:
        session: Database session.

    Returns:
        Health check report.
    """
    logger.info("=" * 60)
    logger.info("[Step 1] Running startup health check...")
    logger.info("=" * 60)

    service = HealthCheckService(session)
    report = await service.run_all_checks()

    # Print summary
    print("\n" + service.format_report())

    return report


async def run_daily_selection_task(session) -> dict[str, Any]:
    """Run daily selection task.

    Args:
        session: Database session.

    Returns:
        Task result.
    """
    logger.info("\n" + "=" * 60)
    logger.info("[Step 2] Running daily selection task...")
    logger.info("=" * 60)

    result = await run_daily_selection(session)

    logger.info(f"Task result: success={result.get('success')}")
    logger.info(f"  Products: {result.get('products_count', 0)}")
    logger.info(f"  New products: {result.get('new_products_count', 0)}")
    logger.info(f"  Matched: {result.get('matched_count', 0)}")
    logger.info(f"  Report sent: {result.get('report_sent', False)}")

    return result


async def get_top_opportunities(session, limit: int = 5) -> list[dict]:
    """Get top opportunities from database.

    Args:
        session: Database session.
        limit: Number of top records.

    Returns:
        List of opportunity data.
    """
    query = (
        select(OpportunityScore)
        .order_by(OpportunityScore.total_score.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    scores = result.scalars().all()

    opportunities = []
    for score in scores:
        # Get product
        product_query = select(Product).where(Product.id == score.product_id)
        product_result = await session.execute(product_query)
        product = product_result.scalar_one_or_none()

        opportunities.append({
            "product_id": score.product_id,
            "product_name": product.name if product else "Unknown",
            "shop": product.shop if product else "Unknown",
            "price": product.price if product else 0,
            "total_score": score.total_score,
            "recommendation": score.recommendation,
        })

    return opportunities


async def main() -> int:
    """Main function."""
    start_time = datetime.now()

    logger.info("=" * 60)
    logger.info("Phase 21 Task 1: First Production Run Validation")
    logger.info(f"Start time: {start_time.isoformat()}")
    logger.info("=" * 60)

    report: dict[str, Any] = {
        "start_time": start_time.isoformat(),
        "end_time": None,
        "health_check": None,
        "task_result": None,
        "top_opportunities": [],
        "errors": [],
    }

    session_factory = get_async_session_factory()

    try:
        async with session_factory() as session:
            # Step 1: Health check
            health_report = await run_health_check(session)
            report["health_check"] = {
                "is_healthy": health_report["is_healthy"],
                "database": health_report["checks"].get("database", {}),
                "taobao_login": health_report["checks"].get("taobao_login", {}),
                "alibaba_login": health_report["checks"].get("alibaba_login", {}),
                "feishu_config": health_report["checks"].get("feishu_config", {}),
            }

            # Step 2: Run daily selection task
            task_result = await run_daily_selection_task(session)
            report["task_result"] = {
                "success": task_result.get("success"),
                "products_count": task_result.get("products_count", 0),
                "new_products_count": task_result.get("new_products_count", 0),
                "matched_count": task_result.get("matched_count", 0),
                "report_sent": task_result.get("report_sent", False),
            }

            if not task_result.get("success"):
                report["errors"].append({
                    "type": "task_failed",
                    "message": task_result.get("error", "Unknown error"),
                })

            # Step 3: Get top opportunities
            top_opps = await get_top_opportunities(session, limit=5)
            report["top_opportunities"] = top_opps

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        report["errors"].append({
            "type": "validation_error",
            "message": str(e),
        })

    # Finalize report
    end_time = datetime.now()
    report["end_time"] = end_time.isoformat()
    report["duration_seconds"] = (end_time - start_time).total_seconds()

    # Save report
    output_path = Path("storage/phase21_first_run_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\nReport saved: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("Phase 21 First Run Validation Summary")
    print("=" * 60)
    print(f"\nStart time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {report['duration_seconds']:.2f} seconds")

    print("\n--- Health Check ---")
    if report["health_check"]:
        hc = report["health_check"]
        print(f"  System healthy: {hc['is_healthy']}")
        print(f"  Database: {hc['database'].get('message', 'N/A')}")
        print(f"  Taobao: {hc['taobao_login'].get('message', 'N/A')}")
        print(f"  1688: {hc['alibaba_login'].get('message', 'N/A')}")
        print(f"  Feishu: {hc['feishu_config'].get('message', 'N/A')}")

    print("\n--- Task Result ---")
    if report["task_result"]:
        tr = report["task_result"]
        print(f"  Success: {tr['success']}")
        print(f"  Products crawled: {tr['products_count']}")
        print(f"  New products: {tr['new_products_count']}")
        print(f"  Suppliers matched: {tr['matched_count']}")
        print(f"  Report sent: {tr['report_sent']}")

    print("\n--- Top Opportunities ---")
    for i, opp in enumerate(report["top_opportunities"], 1):
        print(f"  {i}. {opp['product_name'][:30]}... (Score: {opp['total_score']:.1f})")

    if report["errors"]:
        print("\n--- Errors ---")
        for err in report["errors"]:
            print(f"  [{err['type']}] {err['message']}")

    print("\n" + "=" * 60)

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
