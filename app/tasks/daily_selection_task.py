"""Daily selection task — Automated product discovery and recommendation pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_task_log import DailyTaskLog
from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.services.product_scoring import ProductScoringService
from app.services.supplier_matching import SupplierMatchingService
from app.services.opportunity_scoring import OpportunityScoringService
from app.services.daily_report import DailyReportGenerator
from app.services.feishu_notification import FeishuNotificationService


# ── Configuration ──────────────────────────────────────────────


def load_selection_config(config_path: str | None = None) -> dict[str, Any]:
    """Load selection task configuration.

    Args:
        config_path: Path to config file.

    Returns:
        Configuration dict.
    """
    if config_path is None:
        config_file = Path(__file__).parent.parent.parent / "config" / "selection_config.json"
    else:
        config_file = Path(config_path)

    default_config = {
        "shops": [],
        "top_count": 10,
        "min_score": 75,
    }

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            default_config.update(config)
        except Exception as e:
            logger.warning(f"Failed to load selection config: {e}")

    return default_config


# ── Task Log Management ────────────────────────────────────────


async def create_task_log(session: AsyncSession, task_name: str) -> DailyTaskLog:
    """Create a new task log entry.

    Args:
        session: Database session.
        task_name: Task name.

    Returns:
        Created log entry.
    """
    log = DailyTaskLog(
        task_name=task_name,
        start_time=datetime.now(),
        status="RUNNING",
    )
    session.add(log)
    await session.flush()
    return log


async def finish_task_log(
    session: AsyncSession,
    log: DailyTaskLog,
    *,
    status: str = "SUCCESS",
    products_count: int = 0,
    new_products_count: int = 0,
    matched_count: int = 0,
    report_sent: bool = False,
    error_message: str | None = None,
) -> None:
    """Finish a task log entry.

    Args:
        session: Database session.
        log: Log entry to update.
        status: Final status.
        products_count: Number of products crawled.
        new_products_count: Number of new products.
        matched_count: Number of matched suppliers.
        report_sent: Whether report was sent.
        error_message: Error message if failed.
    """
    log.end_time = datetime.now()
    log.status = status
    log.products_count = products_count
    log.new_products_count = new_products_count
    log.matched_count = matched_count
    log.report_sent = report_sent
    log.error_message = error_message
    await session.flush()


# ── Failure Notification ───────────────────────────────────────


async def send_failure_notification(
    feishu_service: FeishuNotificationService,
    task_name: str,
    error: str,
) -> None:
    """Send failure notification via feishu.

    Args:
        feishu_service: Feishu notification service.
        task_name: Task name.
        error: Error message.
    """
    message = f"⚠️ 今日选品任务失败\n\n任务: {task_name}\n错误: {error}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    try:
        await feishu_service.send_message(message)
        logger.info("Failure notification sent")
    except Exception as e:
        logger.warning(f"Failed to send failure notification: {e}")


# ── Main Task ──────────────────────────────────────────────────


async def run_daily_selection(
    session: AsyncSession,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Run daily product selection pipeline.

    Flow:
    1. Load configuration
    2. Get target shops
    3. Crawl products (mock for now)
    4. Save new products
    5. Score new products
    6. Match with 1688 suppliers
    7. Calculate opportunity scores
    8. Generate daily report
    9. Send to feishu

    Args:
        session: Database session.
        config_path: Optional config file path.

    Returns:
        Task result dict.
    """
    task_name = "daily_selection"
    logger.info(f"Starting {task_name} task...")

    # Load config
    config = load_selection_config(config_path)
    top_count = config.get("top_count", 10)
    min_score = config.get("min_score", 75)

    # Initialize services
    product_scoring_service = ProductScoringService()
    supplier_matching_service = SupplierMatchingService()
    opportunity_scoring_service = OpportunityScoringService()

    # Create task log
    task_log = await create_task_log(session, task_name)
    await session.commit()

    products_count = 0
    new_products_count = 0
    matched_count = 0
    report_sent = False

    try:
        # Step 1: Get target shops (from config or default)
        shops = config.get("shops", [])
        if not shops:
            # Use default shops for demo
            shops = [
                {"name": "三只松鼠旗舰店", "platform": "tmall"},
                {"name": "良品铺子旗舰店", "platform": "tmall"},
            ]
        logger.info(f"Target shops: {len(shops)}")

        # Step 2: Crawl products (using mock data for stability)
        # In production, this would use real crawlers
        products = _generate_mock_products(shops)
        products_count = len(products)
        logger.info(f"Crawled products: {products_count}")

        # Step 3: Save products and identify new ones
        new_products = []
        for p in products:
            # Check if product already exists
            query = select(Product).where(Product.url == p["url"])
            result = await session.execute(query)
            existing = result.scalar_one_or_none()

            if existing is None:
                # New product
                product = Product(
                    name=p["name"],
                    platform=p["platform"],
                    shop=p["shop"],
                    price=p["price"],
                    category=p.get("category"),
                    url=p["url"],
                    image=p.get("image"),
                    lifecycle_stage="NEW",
                    first_seen_time=datetime.now(),
                    last_seen_time=datetime.now(),
                )
                session.add(product)
                await session.flush()
                product.id = product.id  # Ensure ID is set
                new_products.append(product)
            else:
                # Update existing
                existing.last_seen_time = datetime.now()

        new_products_count = len(new_products)
        logger.info(f"New products: {new_products_count}")

        # Step 4: Score new products
        product_scores = []
        for product in new_products:
            score_data = product_scoring_service.calculate_score(product)
            score = ProductScore(
                product_id=product.id,
                shop_score=score_data["shop_score"],
                price_score=score_data["price_score"],
                category_score=score_data["category_score"],
                newness_score=score_data["newness_score"],
                completeness_score=score_data["completeness_score"],
                total_score=score_data["total_score"],
                recommend_level=score_data["recommend_level"],
            )
            session.add(score)
            product_scores.append((product, score))

        await session.flush()
        logger.info(f"Scored products: {len(product_scores)}")

        # Step 5: Match with 1688 suppliers (via unified ProductMatcher entry)
        for product, product_score in product_scores:
            matches = await supplier_matching_service.match_products_with_matcher(
                session=session,
                product=product,
                top_k=3,
            )
            for m in matches:
                session.add(m)
                matched_count += 1

        await session.flush()
        logger.info(f"Matched suppliers: {matched_count}")

        # Step 6: Calculate opportunity scores
        for product, product_score in product_scores:
            # Get supplier match for this product
            query = (
                select(SupplierMatch)
                .where(SupplierMatch.product_id == product.id)
                .order_by(SupplierMatch.similarity_score.desc())
                .limit(1)
            )
            result = await session.execute(query)
            supplier_match = result.scalar_one_or_none()

            opp_data = opportunity_scoring_service.calculate_opportunity_score(
                product=product,
                product_score=product_score,
                supplier_match=supplier_match,
                supplier_count=3 if supplier_match else 0,
            )

            opp_score = OpportunityScore(
                product_id=product.id,
                new_product_score=opp_data["new_product_score"],
                shop_score=opp_data["shop_score"],
                supplier_score=opp_data["supplier_score"],
                profit_score=opp_data["profit_score"],
                competition_score=opp_data["competition_score"],
                total_score=opp_data["total_score"],
                recommendation=opp_data["recommendation"],
            )
            session.add(opp_score)

        await session.commit()
        logger.info("Opportunity scores calculated")

        # Step 7: Generate daily report
        report_generator = DailyReportGenerator(session)
        report = await report_generator.generate_daily_opportunity_report(limit=top_count)
        logger.info("Daily report generated")

        # Step 8: Send to feishu
        feishu_service = FeishuNotificationService()
        if feishu_service.is_enabled:
            result = await feishu_service.send_daily_report(report)
            report_sent = result.get("success", False)
            logger.info(f"Feishu notification: {'sent' if report_sent else 'failed'}")

        # Update task log
        await finish_task_log(
            session,
            task_log,
            status="SUCCESS",
            products_count=products_count,
            new_products_count=new_products_count,
            matched_count=matched_count,
            report_sent=report_sent,
        )
        await session.commit()

        logger.info(f"Task {task_name} completed successfully")
        return {
            "success": True,
            "products_count": products_count,
            "new_products_count": new_products_count,
            "matched_count": matched_count,
            "report_sent": report_sent,
        }

    except Exception as e:
        logger.error(f"Task {task_name} failed: {e}")

        # Update task log with error
        await finish_task_log(
            session,
            task_log,
            status="FAILED",
            products_count=products_count,
            new_products_count=new_products_count,
            matched_count=matched_count,
            error_message=str(e),
        )
        await session.commit()

        # Send failure notification
        feishu_service = FeishuNotificationService()
        if feishu_service.is_enabled:
            await send_failure_notification(feishu_service, task_name, str(e))

        return {
            "success": False,
            "error": str(e),
        }


def _generate_mock_products(shops: list[dict]) -> list[dict]:
    """Generate mock products for testing.

    Args:
        shops: List of shop configs.

    Returns:
        List of mock product dicts.
    """
    mock_products = []
    mock_items = [
        {"name": "三只松鼠芋泥味蛋皮吐司卷", "price": 69.9, "category": "零食"},
        {"name": "良品铺子鸭脖锁骨套餐", "price": 49.9, "category": "零食"},
        {"name": "完美日记动物眼影盘", "price": 89.9, "category": "美妆"},
    ]

    for i, shop in enumerate(shops):
        for j, item in enumerate(mock_items[:2]):  # 2 items per shop
            mock_products.append({
                "name": item["name"],
                "price": item["price"],
                "shop": shop["name"],
                "platform": shop.get("platform", "taobao"),
                "category": item.get("category"),
                "url": f"https://detail.tmall.com/item.htm?id=mock_{i}_{j}",
                "image": f"https://img.alicdn.com/mock_{i}_{j}.jpg",
            })

    return mock_products


# ── Scheduler Job ──────────────────────────────────────────────


async def daily_selection_job() -> None:
    """Scheduled job entry point for daily selection task.

    This function is called by APScheduler.
    """
    from app.database.base import get_async_session_factory

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        result = await run_daily_selection(session)

    if result.get("success"):
        logger.info(
            "Daily selection completed: {} products, {} new, {} matched",
            result.get("products_count", 0),
            result.get("new_products_count", 0),
            result.get("matched_count", 0),
        )
    else:
        logger.error("Daily selection failed: {}", result.get("error"))
