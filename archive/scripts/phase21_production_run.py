#!/usr/bin/env python3
"""Phase 21 Task 3: Complete Production Run.

执行完整的生产环境运行：
1. 初始化数据库
2. 配置测试店铺
3. 检查登录状态
4. 执行选品任务
5. 生成运行报告

Usage:
    python scripts/phase21_production_run.py
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
from app.database.init_db import init_database, verify_database
from app.services.health_check import HealthCheckService
from app.tasks.daily_selection_task import run_daily_selection, load_selection_config
from app.models.opportunity_score import OpportunityScore
from app.models.product import Product
from app.models.supplier_match import SupplierMatch


# ── Test Shop Configuration ────────────────────────────────────

TEST_SHOPS = [
    {"name": "三只松鼠旗舰店", "platform": "tmall"},
    {"name": "完美日记旗舰店", "platform": "tmall"},
    {"name": "花西子旗舰店", "platform": "tmall"},
]


async def step1_init_database() -> dict[str, Any]:
    """Step 1: Initialize database.

    Returns:
        Initialization result.
    """
    logger.info("=" * 60)
    logger.info("[Step 1] Initializing database...")
    logger.info("=" * 60)

    # Initialize
    init_result = await init_database()

    if init_result["success"]:
        logger.info(f"Database initialized: {len(init_result['tables_existing'])} tables")

        # Verify
        verify_result = await verify_database()
        logger.info(f"Database verified: all_present={verify_result['all_present']}")

        return {
            "init": init_result,
            "verify": verify_result,
        }
    else:
        logger.error(f"Database initialization failed: {init_result['error']}")
        return {"init": init_result, "verify": None}


async def step2_configure_shops() -> dict[str, Any]:
    """Step 2: Configure test shops.

    Returns:
        Configuration result.
    """
    logger.info("\n" + "=" * 60)
    logger.info("[Step 2] Configuring test shops...")
    logger.info("=" * 60)

    # Update selection config
    config_path = Path("config/selection_config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "shops": TEST_SHOPS,
        "top_count": 10,
        "min_score": 75,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    logger.info(f"Configured {len(TEST_SHOPS)} test shops:")
    for shop in TEST_SHOPS:
        logger.info(f"  - {shop['name']} ({shop['platform']})")

    return {"shops": TEST_SHOPS, "config_path": str(config_path)}


async def step3_check_login_status(session) -> dict[str, Any]:
    """Step 3: Check login status.

    Args:
        session: Database session.

    Returns:
        Login status result.
    """
    logger.info("\n" + "=" * 60)
    logger.info("[Step 3] Checking login status...")
    logger.info("=" * 60)

    health_service = HealthCheckService(session)

    # Check Taobao
    taobao_result = await health_service.check_taobao_login()
    logger.info(f"Taobao: {taobao_result.get('status', 'UNKNOWN')} - {taobao_result.get('message', '')}")

    # Check 1688
    alibaba_result = await health_service.check_alibaba_login()
    logger.info(f"1688: {alibaba_result.get('status', 'UNKNOWN')} - {alibaba_result.get('message', '')}")

    return {
        "taobao": taobao_result,
        "alibaba": alibaba_result,
    }


async def step4_run_selection(session) -> dict[str, Any]:
    """Step 4: Run daily selection task.

    Args:
        session: Database session.

    Returns:
        Task result.
    """
    logger.info("\n" + "=" * 60)
    logger.info("[Step 4] Running daily selection task...")
    logger.info("=" * 60)

    result = await run_daily_selection(session)

    logger.info(f"Task success: {result.get('success')}")
    logger.info(f"  Products: {result.get('products_count', 0)}")
    logger.info(f"  New products: {result.get('new_products_count', 0)}")
    logger.info(f"  Matched: {result.get('matched_count', 0)}")
    logger.info(f"  Report sent: {result.get('report_sent', False)}")

    return result


async def step5_get_opportunities(session, limit: int = 10) -> list[dict]:
    """Step 5: Get top opportunities.

    Args:
        session: Database session.
        limit: Number of top records.

    Returns:
        List of opportunity data.
    """
    logger.info("\n" + "=" * 60)
    logger.info(f"[Step 5] Getting top {limit} opportunities...")
    logger.info("=" * 60)

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

        # Get supplier match
        match_query = (
            select(SupplierMatch)
            .where(SupplierMatch.product_id == score.product_id)
            .order_by(SupplierMatch.similarity_score.desc())
            .limit(1)
        )
        match_result = await session.execute(match_query)
        match = match_result.scalar_one_or_none()

        opp = {
            "product_id": score.product_id,
            "product_name": product.name if product else "Unknown",
            "shop": product.shop if product else "Unknown",
            "price": product.price if product else 0,
            "total_score": score.total_score,
            "recommendation": score.recommendation,
        }

        if match:
            opp["supplier_title"] = match.supplier_title
            opp["supplier_price"] = match.supplier_price
            opp["profit_margin"] = match.profit_margin

        opportunities.append(opp)
        logger.info(f"  {len(opportunities)}. {opp['product_name'][:30]}... (Score: {opp['total_score']:.1f})")

    return opportunities


async def main() -> int:
    """Main function."""
    start_time = datetime.now()

    logger.info("=" * 60)
    logger.info("Phase 21 Task 3: Complete Production Run")
    logger.info(f"Start time: {start_time.isoformat()}")
    logger.info("=" * 60)

    report: dict[str, Any] = {
        "start_time": start_time.isoformat(),
        "end_time": None,
        "shops": [],
        "products": 0,
        "new_products": 0,
        "supplier_matches": 0,
        "opportunities": [],
        "top10": [],
        "report_status": "pending",
        "errors": [],
    }

    session_factory = get_async_session_factory()

    try:
        # Step 1: Initialize database
        init_result = await step1_init_database()
        if not init_result.get("init", {}).get("success"):
            report["errors"].append({
                "step": "init_database",
                "message": init_result.get("init", {}).get("error", "Unknown error"),
            })

        async with session_factory() as session:
            # Step 2: Configure shops
            shop_result = await step2_configure_shops()
            report["shops"] = shop_result["shops"]

            # Step 3: Check login status
            login_result = await step3_check_login_status(session)
            report["login_status"] = login_result

            # Step 4: Run selection task
            task_result = await step4_run_selection(session)
            report["products"] = task_result.get("products_count", 0)
            report["new_products"] = task_result.get("new_products_count", 0)
            report["supplier_matches"] = task_result.get("matched_count", 0)
            report["report_status"] = "sent" if task_result.get("report_sent") else "not_sent"

            if not task_result.get("success"):
                report["errors"].append({
                    "step": "run_selection",
                    "message": task_result.get("error", "Unknown error"),
                })

            # Step 5: Get opportunities
            opportunities = await step5_get_opportunities(session, limit=10)
            report["opportunities"] = opportunities
            report["top10"] = opportunities[:10]

    except Exception as e:
        logger.error(f"Production run failed: {e}")
        report["errors"].append({
            "step": "main",
            "message": str(e),
        })

    # Finalize report
    end_time = datetime.now()
    report["end_time"] = end_time.isoformat()
    report["duration_seconds"] = (end_time - start_time).total_seconds()

    # Save report
    output_path = Path("storage/phase21_production_run_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\nReport saved: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("Phase 21 Production Run Summary")
    print("=" * 60)
    print(f"\nStart time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {report['duration_seconds']:.2f} seconds")

    print(f"\n--- Shops ---")
    for shop in report["shops"]:
        print(f"  - {shop['name']}")

    print(f"\n--- Results ---")
    print(f"  Products crawled: {report['products']}")
    print(f"  New products: {report['new_products']}")
    print(f"  Supplier matches: {report['supplier_matches']}")
    print(f"  Report status: {report['report_status']}")

    print(f"\n--- Top Opportunities ---")
    for i, opp in enumerate(report["top10"][:5], 1):
        print(f"  {i}. {opp['product_name'][:35]}... (Score: {opp['total_score']:.1f})")

    if report["errors"]:
        print(f"\n--- Errors ({len(report['errors'])}) ---")
        for err in report["errors"]:
            print(f"  [{err['step']}] {err['message'][:50]}...")

    print("\n" + "=" * 60)

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
