"""Database initialization service — Create all ORM tables."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database.base import Base, get_async_engine, get_engine


# Import all models to ensure they are registered with Base
from app.models import (  # noqa: F401
    AssistantHistory,
    CrawlLog,
    CrawlerStatus,
    DailyReport,
    DailyReportItem,
    DailyTaskLog,
    FailedTask,
    LoginSession,
    OpportunityScore,
    Product,
    ProductHistory,
    ProductScore,
    ProductStrategy,
    ProductTag,
    ProductTagRelation,
    RecommendationPublishRecord,
    RecommendationReview,
    RecommendationStatus,
    ScoringConfig,
    ShopRegistry,
    SupplierMatch,
    SupplierProductDB,
    SupplyChainMatch,
    TaskExecution,
)


# ── Table List ─────────────────────────────────────────────────

REQUIRED_TABLES = [
    "products",
    "product_scores",
    "supplier_matches",
    "supplier_products",
    "opportunity_scores",
    "login_sessions",
    "daily_task_logs",
    "shop_registry",
    "crawl_logs",
    "crawler_status",
    "task_executions",
    "failed_tasks",
    "product_history",
    "daily_reports",
    "daily_report_items",
    "assistant_history",
    "product_strategies",
    "product_tags",
    "product_tag_relations",
    "recommendation_reviews",
    "recommendation_status",
    "recommendation_publish_records",
    "scoring_configs",
    "supply_chain_matches",
]


# ── Sync Initialization ────────────────────────────────────────


def init_database_sync() -> dict[str, Any]:
    """Initialize database synchronously.

    Creates all ORM tables if they don't exist.

    Returns:
        Initialization result dict.
    """
    logger.info("Initializing database (sync)...")

    result = {
        "success": False,
        "tables_created": [],
        "tables_existing": [],
        "error": None,
    }

    try:
        engine = get_engine()

        # Create all tables
        Base.metadata.create_all(bind=engine)

        # Check which tables exist
        with engine.connect() as conn:
            insp_result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            existing_tables = [row[0] for row in insp_result.fetchall()]

        for table in REQUIRED_TABLES:
            if table in existing_tables:
                result["tables_existing"].append(table)
            else:
                result["tables_created"].append(table)

        result["success"] = True
        logger.info(f"Database initialized: {len(result['tables_existing'])} tables verified")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Database initialization failed: {e}")

    return result


# ── Async Initialization ───────────────────────────────────────


async def init_database() -> dict[str, Any]:
    """Initialize database asynchronously.

    Creates all ORM tables if they don't exist.

    Returns:
        Initialization result dict.
    """
    logger.info("Initializing database (async)...")

    result = {
        "success": False,
        "tables_created": [],
        "tables_existing": [],
        "error": None,
    }

    try:
        engine = get_async_engine()

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Check which tables exist
        async with engine.connect() as conn:
            insp_result = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            existing_tables = [row[0] for row in insp_result.fetchall()]

        for table in REQUIRED_TABLES:
            if table in existing_tables:
                result["tables_existing"].append(table)
            else:
                result["tables_created"].append(table)

        result["success"] = True
        logger.info(f"Database initialized: {len(result['tables_existing'])} tables verified")

        await engine.dispose()

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Database initialization failed: {e}")

    return result


# ── Verification ───────────────────────────────────────────────


async def verify_database() -> dict[str, Any]:
    """Verify database initialization.

    Returns:
        Verification result dict.
    """
    logger.info("Verifying database...")

    result = {
        "connected": False,
        "tables_present": [],
        "tables_missing": [],
        "all_present": False,
    }

    try:
        engine = get_async_engine()

        # Test connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            result["connected"] = True

            # Get existing tables
            insp_result = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            existing_tables = [row[0] for row in insp_result.fetchall()]

        # Check required tables
        for table in REQUIRED_TABLES:
            if table in existing_tables:
                result["tables_present"].append(table)
            else:
                result["tables_missing"].append(table)

        result["all_present"] = len(result["tables_missing"]) == 0

        await engine.dispose()

        if result["all_present"]:
            logger.info(f"Database verified: {len(result['tables_present'])} tables present")
        else:
            logger.warning(f"Database verification: {len(result['tables_missing'])} tables missing")

    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        result["error"] = str(e)

    return result


# ── CLI Entry Point ────────────────────────────────────────────


def print_result(result: dict[str, Any]) -> None:
    """Print initialization result."""
    print("\n" + "=" * 50)
    print("Database Initialization Result")
    print("=" * 50)

    if result.get("success"):
        print(f"\nStatus: SUCCESS")
        print(f"Tables verified: {len(result.get('tables_existing', []))}")
        if result.get("tables_created"):
            print(f"Tables created: {len(result['tables_created'])}")
    else:
        print(f"\nStatus: FAILED")
        print(f"Error: {result.get('error', 'Unknown')}")

    print("\n" + "=" * 50)


async def main() -> int:
    """Main entry point for CLI."""
    logger.info("Database initialization started...")

    # Initialize
    result = await init_database()

    # Verify
    if result["success"]:
        verify_result = await verify_database()
        result["verification"] = verify_result

    # Print result
    print_result(result)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
