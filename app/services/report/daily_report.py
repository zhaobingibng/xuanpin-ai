"""Daily product selection report generator."""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.history_repository import HistoryRepository
from app.database.report_repository import ReportRepository
from app.models.daily_report import DailyReport, DailyReportItem
from app.services.analytics.analyzer import TrendAnalyzer
from app.services.decision.engine import ProductDecisionEngine
from app.services.lifecycle.analyzer import LifecycleAnalyzer
from app.services.product_service import ProductService
from app.services.recommendation.ranker import RecommendationRanker
from app.services.scoring.product_scorer import ProductScorer


class DailyReportService:
    """每日选品报告服务。

    数据流程: Product → ProductHistory → ProductScorer → Ranking → DailyReport。

    Usage::

        svc = DailyReportService(session)
        report = await svc.generate(limit=20)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._product_service = ProductService(session)
        self._history_repo = HistoryRepository(session)
        self._report_repo = ReportRepository(session)
        self._scorer = ProductScorer()
        self._lifecycle = LifecycleAnalyzer(session)
        self._decision = ProductDecisionEngine()
        self._ranker = RecommendationRanker()

    # ── Public API ────────────────────────────────────────────

    async def generate(self, limit: int = 20) -> dict[str, Any]:
        """生成每日选品报告。

        Args:
            limit: 报告中商品数量上限，默认 TOP 20。

        Returns:
            包含 date, total, hot_products, potential_products,
            average_score, items 的报告字典。
        """
        # 1. 查询所有商品
        products = await self._product_service.list_all(limit=10_000)

        if not products:
            logger.info("[DailyReport] 无商品数据")
            return {
                "date": date.today().isoformat(),
                "total": 0,
                "hot_products": 0,
                "potential_products": 0,
                "average_score": 0.0,
                "items": [],
            }

        # 2. 逐个评分 + 生命周期分析 + 趋势 + 决策
        scored: list[dict[str, Any]] = []
        for product in products:
            history = list(await self._history_repo.get_history(product.id))
            result = self._scorer.calculate_score(product, history or None)
            lifecycle_result = await self._lifecycle.analyze(product.id)
            decision_result = self._decision.decide(
                product, result["score"], lifecycle_result["stage"]
            )
            trend_score = 50.0
            if history and len(history) >= 2:
                analyzer = TrendAnalyzer(history)
                trend_score = analyzer.calculate_trend_score()["trend_score"]
            scored.append({
                "product_id": product.id,
                "name": product.name,
                "platform": product.platform,
                "image": product.image or "",
                "price": product.price,
                "score": result["score"],
                "level": result["level"],
                "reasons": result["reasons"],
                "lifecycle": lifecycle_result["stage"],
                "decision": decision_result,
                "trend_score": trend_score,
            })

        # 3. 推荐排序
        ranked = self._ranker.rank(scored)
        top = ranked[:limit]

        # 4. 重新分配 rank（ranker 已分配，保持即可）

        # 5. 统计
        hot = sum(1 for e in top if e.get("level") == "爆款")
        potential = sum(1 for e in top if e.get("level") == "潜力")
        avg = round(sum(e["score"] for e in top) / len(top), 1) if top else 0.0

        report = {
            "date": date.today().isoformat(),
            "total": len(top),
            "hot_products": hot,
            "potential_products": potential,
            "average_score": avg,
            "items": top,
        }

        logger.info(
            "[DailyReport] date={}, total={}, hot={}, potential={}, avg={}",
            report["date"], report["total"], hot, potential, avg,
        )
        return report

    # ── Generate + Save ────────────────────────────────────────

    async def generate_and_save(self, limit: int = 20) -> dict[str, Any]:
        """生成报告并持久化到数据库。

        同一天重复生成时执行 update（覆盖旧记录），不新增重复记录。

        Returns:
            与 generate() 相同结构的报告字典。
        """
        report = await self.generate(limit=limit)
        today = date.today()

        # 检查当天是否已有日报
        existing = await self._report_repo.find_by_date(today)

        if existing is not None:
            # update: 覆盖字段 + 删除旧 items + 保存新 items
            existing.total = report["total"]
            existing.hot_products = report["hot_products"]
            existing.potential_products = report["potential_products"]
            existing.average_score = report["average_score"]
            await self._session.flush()

            # 删除旧 items
            await self._session.execute(
                delete(DailyReportItem).where(DailyReportItem.report_id == existing.id)
            )
            await self._session.flush()

            # 保存新 items
            await self._report_repo.save_items(existing.id, report["items"])
            logger.info("[DailyReport] 更新已有日报: id={}, date={}", existing.id, today)
        else:
            # 新建
            db_report = DailyReport(
                report_date=today,
                total=report["total"],
                hot_products=report["hot_products"],
                potential_products=report["potential_products"],
                average_score=report["average_score"],
            )
            await self._report_repo.create_report(db_report)
            await self._report_repo.save_items(db_report.id, report["items"])
            logger.info("[DailyReport] 新建日报: id={}, date={}", db_report.id, today)

        await self._session.commit()
        return report
