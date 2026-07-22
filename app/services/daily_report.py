"""Daily opportunity report generator."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.opportunity_score import OpportunityScore
from app.models.supplier_match import SupplierMatch


class DailyReportGenerator:
    """每日选品机会报告生成器。

    功能：
    - 查询 TOP N OpportunityScore
    - 生成 Markdown 格式日报文本
    - 支持飞书推送

    使用示例：
        generator = DailyReportGenerator(session)
        report = await generator.generate_daily_opportunity_report()
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            session: Async SQLAlchemy session.
        """
        self._session = session

    async def get_top_opportunities(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get top opportunity scores with related data.

        Args:
            limit: Number of top records to fetch.

        Returns:
            List of opportunity data dicts.
        """
        # Query top opportunity scores
        query = (
            select(OpportunityScore)
            .order_by(OpportunityScore.total_score.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        scores = result.scalars().all()

        opportunities = []
        for score in scores:
            # Get related product
            product_query = select(Product).where(Product.id == score.product_id)
            product_result = await self._session.execute(product_query)
            product = product_result.scalar_one_or_none()

            # Get related supplier match
            match_query = (
                select(SupplierMatch)
                .where(SupplierMatch.product_id == score.product_id)
                .order_by(SupplierMatch.similarity_score.desc())
                .limit(1)
            )
            match_result = await self._session.execute(match_query)
            supplier_match = match_result.scalar_one_or_none()

            opportunities.append({
                "product": product,
                "score": score,
                "supplier_match": supplier_match,
            })

        return opportunities

    def format_report(
        self,
        opportunities: list[dict[str, Any]],
        date: datetime | None = None,
    ) -> str:
        """Format opportunities as Markdown report.

        Args:
            opportunities: List of opportunity data dicts.
            date: Report date (default: today).

        Returns:
            Formatted Markdown report text.
        """
        if date is None:
            date = datetime.now()

        lines = [
            f"# 今日选品机会 ({date.strftime('%Y-%m-%d')})",
            "",
            f"共发现 {len(opportunities)} 个值得跟卖的机会：",
            "",
        ]

        for i, opp in enumerate(opportunities, 1):
            product = opp["product"]
            score = opp["score"]
            match = opp["supplier_match"]

            lines.append(f"## {i}. {product.name if product else 'Unknown'}")
            lines.append("")

            if product:
                lines.append(f"- 店铺：{product.shop}")
                lines.append(f"- 淘宝价格：{product.price:.1f} 元")
            else:
                lines.append("- 店铺：未知")
                lines.append("- 淘宝价格：未知")

            if match:
                lines.append(f"- 1688成本：{match.supplier_price:.1f} 元")
                lines.append(f"- 预计利润：{match.estimated_profit:.1f} 元")
                lines.append(f"- 利润率：{match.profit_margin:.1f}%")
            else:
                lines.append("- 1688成本：未匹配")
                lines.append("- 预计利润：--")
                lines.append("- 利润率：--")

            lines.append(f"- 机会指数：{score.total_score:.1f}")
            lines.append(f"- 推荐等级：{score.recommendation}")
            lines.append("")

            # 推荐理由
            lines.append("**推荐理由：**")
            reasons = []
            if product and product.lifecycle_stage == "NEW":
                reasons.append("- 新品发现")
            if product and ("旗舰" in product.shop or "官方" in product.shop):
                reasons.append("- 头部店铺")
            if match:
                reasons.append("- 找到供应链")
                if match.profit_margin >= 50:
                    reasons.append("- 高利润空间")
            if score.total_score >= 90:
                reasons.append("- 综合评分优秀")

            if reasons:
                lines.extend(reasons)
            else:
                lines.append("- 值得关注")

            lines.append("")
            lines.append("---")
            lines.append("")

        # Summary
        lines.append("## 数据统计")
        lines.append("")
        lines.append(f"- 报告时间：{date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"- 推荐商品数：{len(opportunities)}")

        high_profit_count = sum(
            1 for opp in opportunities
            if opp["supplier_match"] and opp["supplier_match"].profit_margin >= 50
        )
        lines.append(f"- 高利润商品（利润率>=50%）：{high_profit_count}")

        return "\n".join(lines)

    async def generate_daily_opportunity_report(
        self,
        limit: int = 10,
    ) -> str:
        """Generate daily opportunity report.

        Args:
            limit: Number of top opportunities to include.

        Returns:
            Formatted report text.
        """
        logger.info(f"Generating daily opportunity report (top {limit})...")

        opportunities = await self.get_top_opportunities(limit=limit)

        if not opportunities:
            return "今日暂无值得跟卖的新品机会。"

        report = self.format_report(opportunities)

        logger.info(f"Report generated: {len(opportunities)} opportunities")
        return report


async def daily_report_task(
    session: AsyncSession,
    feishu_service: Any = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Daily report task entry point.

    This function is designed to be called by a scheduler (APScheduler/Celery).

    Args:
        session: Database session.
        feishu_service: Optional FeishuNotificationService instance.
        limit: Number of top opportunities.

    Returns:
        Task result dict.
    """
    logger.info("Starting daily report task...")

    try:
        # Generate report
        generator = DailyReportGenerator(session)
        report = await generator.generate_daily_opportunity_report(limit=limit)

        # Send to feishu if configured
        feishu_result = None
        if feishu_service and feishu_service.is_enabled:
            feishu_result = await feishu_service.send_daily_report(report)
            logger.info(f"Feishu notification sent: {feishu_result}")

        return {
            "success": True,
            "report": report,
            "feishu_result": feishu_result,
        }

    except Exception as e:
        logger.error(f"Daily report task failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
