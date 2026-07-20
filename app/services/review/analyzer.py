"""Recommendation review analyzer — closed-loop feedback system."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.history_repository import HistoryRepository
from app.database.report_repository import ReportRepository
from app.database.review_repository import ReviewRepository
from app.models.recommendation_review import RecommendationReview


class RecommendationReviewService:
    """推荐复盘服务 — 评估历史推荐的有效性。

    闭环流程：推荐 → 销售变化 → 效果判断 → 反馈分析

    判断规则（基于推荐后 3 天 ProductHistory）：
      - SUCCESS: 销量增长 >=30% 或 trend_score 提升 >=20
      - FAILED:  销量下降 >30% 或 趋势明显下降 (trend_change <= -20)
      - NORMAL:  其他

    Usage::

        svc = RecommendationReviewService(session)
        result = await svc.review_daily(date(2026, 7, 12))
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._report_repo = ReportRepository(session)
        self._history_repo = HistoryRepository(session)
        self._review_repo = ReviewRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def review_daily(self, review_date: date | None = None) -> dict[str, Any]:
        """对指定日期的推荐进行复盘。

        Args:
            review_date: 要复盘的推荐日期。默认复盘 7 天前。

        Returns:
            {
                "date": str,
                "total": int,
                "success": int,
                "normal": int,
                "failed": int,
                "accuracy": float,
                "insights": list[str],
            }
        """
        if review_date is None:
            review_date = date.today() - timedelta(days=3)

        # 查找该日期的推荐报告
        report = await self._report_repo.find_by_date(review_date)
        if report is None:
            logger.info("[Review] 无 {} 的推荐记录", review_date)
            return {
                "date": review_date.isoformat(),
                "total": 0,
                "success": 0,
                "normal": 0,
                "failed": 0,
                "accuracy": 0.0,
                "insights": ["无推荐记录"],
            }

        # 获取报告的所有推荐商品
        report_with_items = await self._report_repo.get_report_detail(report.id)
        if report_with_items is None or not report_with_items.items:
            return {
                "date": review_date.isoformat(),
                "total": 0,
                "success": 0,
                "normal": 0,
                "failed": 0,
                "accuracy": 0.0,
                "insights": ["无推荐商品"],
            }

        items = report_with_items.items
        success_count = 0
        normal_count = 0
        failed_count = 0
        insights: list[str] = []

        for item in items:
            result = await self._review_single_item(item, review_date)

            review = RecommendationReview(
                recommendation_id=item.id,
                product_id=item.product_id,
                review_date=date.today(),
                result=result["result"],
                sales_change=result["sales_change"],
                trend_change=result["trend_change"],
            )
            await self._review_repo.save_review(review)

            if result["result"] == "SUCCESS":
                success_count += 1
            elif result["result"] == "FAILED":
                failed_count += 1
            else:
                normal_count += 1

        total = len(items)
        accuracy = round(success_count / total * 100, 1) if total > 0 else 0.0

        # 生成洞察
        insights = self._generate_insights(
            total, success_count, normal_count, failed_count, accuracy
        )

        try:
            await self._session.commit()
        except Exception as e:
            logger.warning("[Review] 保存复盘结果失败: {}", e)

        report_result = {
            "date": review_date.isoformat(),
            "total": total,
            "success": success_count,
            "normal": normal_count,
            "failed": failed_count,
            "accuracy": accuracy,
            "insights": insights,
        }

        logger.info(
            "[Review] date={}, total={}, success={}, normal={}, failed={}, accuracy={}%",
            review_date, total, success_count, normal_count, failed_count, accuracy,
        )
        return report_result

    # ── Single item review ────────────────────────────────────

    async def _review_single_item(
        self, item: Any, recommendation_date: date
    ) -> dict[str, Any]:
        """复盘单个推荐商品。

        比较推荐日前后的历史数据，判断推荐效果。
        """
        product_id = item.product_id
        history = list(await self._history_repo.get_history(product_id, limit=30))

        if not history:
            return {"result": "NORMAL", "sales_change": 0.0, "trend_change": 0.0}

        # 分离推荐前和推荐后的历史数据
        baseline_sales, baseline_viewers = self._get_baseline(
            history, recommendation_date
        )
        latest_sales, latest_viewers = self._get_latest(history)

        # 计算变化
        sales_change = self._calc_change(baseline_sales, latest_sales)
        viewers_change = self._calc_change(baseline_viewers, latest_viewers)

        # 使用 viewers 作为 trend 的代理指标
        trend_change = viewers_change

        # 判断结果
        result = self._judge_result(sales_change, trend_change)

        return {
            "result": result,
            "sales_change": round(sales_change, 1),
            "trend_change": round(trend_change, 1),
        }

    # ── Data helpers ──────────────────────────────────────────

    @staticmethod
    def _get_baseline(
        history: list[Any], recommendation_date: date
    ) -> tuple[float, float]:
        """获取推荐前的基准值（推荐日期及之前的记录）。

        history 按时间降序排列，所以推荐日期前的记录在末尾。
        """
        baseline_records = [
            h for h in history
            if hasattr(h, 'record_time') and h.record_time and
            h.record_time.date() <= recommendation_date
        ]

        if not baseline_records:
            # 无推荐前数据，使用最早的记录
            if history:
                oldest = history[-1]
                return float(oldest.sales_24h), float(oldest.viewers)
            return 0.0, 0.0

        # 取推荐前记录的均值作为基准
        avg_sales = sum(h.sales_24h for h in baseline_records) / len(baseline_records)
        avg_viewers = sum(h.viewers for h in baseline_records) / len(baseline_records)
        return avg_sales, avg_viewers

    @staticmethod
    def _get_latest(history: list[Any]) -> tuple[float, float]:
        """获取最新的历史数据（history[0] 是最新的）。"""
        if not history:
            return 0.0, 0.0
        latest = history[0]
        return float(latest.sales_24h), float(latest.viewers)

    @staticmethod
    def _calc_change(baseline: float, current: float) -> float:
        """计算百分比变化。"""
        if baseline <= 0:
            if current > 0:
                return 100.0
            return 0.0
        return ((current - baseline) / baseline) * 100.0

    # ── Judgement logic ───────────────────────────────────────

    @staticmethod
    def _judge_result(sales_change: float, trend_change: float) -> str:
        """根据变化判断复盘结果。

        SUCCESS: 销量增长 >=30% 或 trend 提升 >=20
        FAILED:  销量下降 >30% 或 trend 下降 <= -20
        NORMAL:  其他
        """
        # SUCCESS 条件
        if sales_change >= 30 or trend_change >= 20:
            return "SUCCESS"

        # FAILED 条件
        if sales_change <= -30 or trend_change <= -20:
            return "FAILED"

        return "NORMAL"

    # ── Insights ──────────────────────────────────────────────

    @staticmethod
    def _generate_insights(
        total: int,
        success: int,
        normal: int,
        failed: int,
        accuracy: float,
    ) -> list[str]:
        """生成复盘洞察。"""
        insights: list[str] = []

        insights.append(f"共复盘 {total} 个推荐")

        if accuracy >= 60:
            insights.append(f"推荐准确率 {accuracy}%，表现优秀")
        elif accuracy >= 40:
            insights.append(f"推荐准确率 {accuracy}%，表现一般")
        else:
            insights.append(f"推荐准确率 {accuracy}%，需要优化推荐策略")

        if success > 0:
            insights.append(f"{success} 个推荐有效（销量/趋势明显增长）")

        if failed > 0:
            ratio = round(failed / total * 100, 1) if total > 0 else 0
            insights.append(f"{failed} 个推荐失败（{ratio}%），建议调整筛选标准")

        if normal > total * 0.5:
            insights.append("多数推荐效果不明显，建议提高推荐阈值")

        return insights
