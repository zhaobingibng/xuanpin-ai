"""RecommendationPoolRepository — 推荐池聚合查询（纯只读，JOIN 多表）(Phase 46.2).

推荐池 = daily_report_items + products + supplier_matches(rank=1) + recommendation_status
零写操作，不修改已有 Product/SupplierMatch/DailyReportItem 等任何业务数据。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.models.recommendation_status import RecommendationStatus
from app.models.supplier_match import SupplierMatch


class RecommendationPoolRepository:
    """推荐池聚合查询（纯只读）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Date helpers ───────────────────────────────────────────

    async def get_latest_report_date(self) -> date | None:
        """返回最新 DailyReport.report_date，无数据返回 None。"""
        stmt = (
            select(DailyReport.report_date)
            .order_by(DailyReport.report_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row else None

    # ── Pool list (aggregation) ────────────────────────────────

    async def list_pool(
        self,
        report_date: date | None = None,
        status: str | None = None,
        min_score: float | None = None,
        platform: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """聚合查询推荐池列表。

        逐条构建聚合字典（避免复杂 JOIN 的笛卡尔积问题）。
        先查 daily_report_items → 再批量查关联数据。

        Returns:
            [{product_id, rank, name, platform, shop, image, price,
              score, level, reasons, final_score, action,
              best_supplier_title, best_supplier_price, best_supplier_url,
              estimated_profit, profit_margin, match_score, supplier_count,
              review_status, review_notes, reviewed_at}]
        """
        target_date = report_date
        if target_date is None:
            target_date = await self.get_latest_report_date()
        if target_date is None:
            return []

        # 1. 找到目标日期的 DailyReport
        report_stmt = select(DailyReport).where(
            DailyReport.report_date == target_date
        )
        report_result = await self._session.execute(report_stmt)
        daily_report = report_result.scalar_one_or_none()
        if daily_report is None:
            return []

        # 2. 查该 report 的所有 items
        item_stmt = (
            select(DailyReportItem)
            .where(DailyReportItem.report_id == daily_report.id)
            .order_by(DailyReportItem.rank)
        )
        item_result = await self._session.execute(item_stmt)
        items = list(item_result.scalars().all())

        if not items:
            return []

        # 3. 批量取 product / supplier_match / status
        product_ids = [i.product_id for i in items]

        products_map = await self._batch_get_products(product_ids)
        best_matches_map = await self._batch_get_best_matches(product_ids)
        supplier_counts_map = await self._batch_get_supplier_counts(product_ids)
        statuses_map = await self._batch_get_statuses(product_ids, target_date)

        # 4. 聚合为 dict 列表
        rows: list[dict] = []
        for item in items:
            p = products_map.get(item.product_id)
            if p is None:
                continue

            bm = best_matches_map.get(item.product_id) or {}
            rs = statuses_map.get(item.product_id)

            row = {
                "product_id": item.product_id,
                "rank": item.rank,
                "name": p.name,
                "platform": p.platform,
                "shop": p.shop,
                "image": p.image or "",
                "price": p.price,
                "score": item.score,
                "level": item.level,
                "reasons": item.reasons,
                "action": self._extract_action(item.reasons),
                # 供应商聚合
                "best_supplier_title": bm.get("supplier_title", ""),
                "best_supplier_price": bm.get("supplier_price"),
                "best_supplier_url": bm.get("supplier_url", ""),
                "estimated_profit": bm.get("estimated_profit", 0.0),
                "profit_margin": bm.get("profit_margin", 0.0),
                "match_score": bm.get("similarity_score"),
                "supplier_count": supplier_counts_map.get(item.product_id, 0),
                # 审核状态
                "review_status": rs.status if rs else "NEW",
                "review_notes": rs.review_notes if rs else None,
                "reviewed_at": rs.reviewed_at.isoformat() if rs and rs.reviewed_at else None,
            }
            rows.append(row)

        # 5. 内存筛选（避免复杂 SQL 条件）
        if status is not None:
            rows = [r for r in rows if r["review_status"] == status]
        if min_score is not None:
            rows = [r for r in rows if r["score"] >= min_score]
        if platform is not None:
            rows = [r for r in rows if r["platform"] == platform]

        return rows[offset : offset + limit]

    # ── Pool detail ────────────────────────────────────────────

    async def get_pool_detail(
        self, product_id: int, report_date: date | None = None
    ) -> dict | None:
        """单条推荐池详情 — 含全部 supplier_matches（不只 best 一条）。"""
        target_date = report_date
        if target_date is None:
            target_date = await self.get_latest_report_date()
        if target_date is None:
            return None

        # product
        p_stmt = select(Product).where(Product.id == product_id)
        p_result = await self._session.execute(p_stmt)
        product = p_result.scalar_one_or_none()
        if product is None:
            return None

        # daily_report_item
        report_stmt = select(DailyReport).where(
            DailyReport.report_date == target_date
        )
        report_result = await self._session.execute(report_stmt)
        daily_report = report_result.scalar_one_or_none()
        if daily_report is None:
            return None

        item_stmt = select(DailyReportItem).where(
            DailyReportItem.report_id == daily_report.id,
            DailyReportItem.product_id == product_id,
        )
        item_result = await self._session.execute(item_stmt)
        item = item_result.scalar_one_or_none()

        # 全部 supplier_matches
        sm_stmt = (
            select(SupplierMatch)
            .where(SupplierMatch.product_id == product_id)
            .order_by(SupplierMatch.similarity_score.desc())
        )
        sm_result = await self._session.execute(sm_stmt)
        all_matches = list(sm_result.scalars().all())

        # review status
        rs_stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id == product_id,
            RecommendationStatus.report_date == target_date,
        )
        rs_result = await self._session.execute(rs_stmt)
        review_status = rs_result.scalar_one_or_none()

        return {
            "product_id": product.id,
            "name": product.name,
            "platform": product.platform,
            "shop": product.shop,
            "image": product.image or "",
            "price": product.price,
            "url": product.url or "",
            "lifecycle_stage": product.lifecycle_stage,
            "rank": item.rank if item else None,
            "score": item.score if item else None,
            "level": item.level if item else None,
            "reasons": item.reasons if item else None,
            "supplier_matches": [
                {
                    "supplier_product_id": sm.supplier_product_id,
                    "supplier_title": sm.supplier_title,
                    "supplier_price": sm.supplier_price,
                    "supplier_url": sm.supplier_url or "",
                    "similarity_score": sm.similarity_score,
                    "estimated_profit": sm.estimated_profit,
                    "profit_margin": sm.profit_margin,
                    "rank": sm.rank,
                }
                for sm in all_matches
            ],
            "review_status": review_status.status if review_status else "NEW",
            "review_notes": review_status.review_notes if review_status else None,
            "reviewed_at": (
                review_status.reviewed_at.isoformat()
                if review_status and review_status.reviewed_at
                else None
            ),
        }

    # ── Batch helpers (internal) ───────────────────────────────

    async def _batch_get_products(self, ids: list[int]) -> dict[int, Product]:
        if not ids:
            return {}
        stmt = select(Product).where(Product.id.in_(ids))
        result = await self._session.execute(stmt)
        return {p.id: p for p in result.scalars().all()}

    async def _batch_get_best_matches(
        self, ids: list[int]
    ) -> dict[int, dict]:
        """返回 {product_id: {supplier_title, supplier_price, ...}}（仅 rank=1）。"""
        if not ids:
            return {}
        # 子查询：每个 product 取 rank 最小的 supplier_match
        from sqlalchemy import and_

        stmt = (
            select(SupplierMatch)
            .where(
                and_(
                    SupplierMatch.product_id.in_(ids),
                    SupplierMatch.rank == 1,
                )
            )
        )
        result = await self._session.execute(stmt)
        return {
            sm.product_id: {
                "supplier_title": sm.supplier_title,
                "supplier_price": sm.supplier_price,
                "supplier_url": sm.supplier_url or "",
                "estimated_profit": sm.estimated_profit,
                "profit_margin": sm.profit_margin,
                "similarity_score": sm.similarity_score,
            }
            for sm in result.scalars().all()
        }

    async def _batch_get_supplier_counts(
        self, ids: list[int]
    ) -> dict[int, int]:
        """返回 {product_id: supplier_count}。"""
        if not ids:
            return {}
        from sqlalchemy import func as sa_func

        stmt = (
            select(
                SupplierMatch.product_id,
                sa_func.count(SupplierMatch.id).label("cnt"),
            )
            .where(SupplierMatch.product_id.in_(ids))
            .group_by(SupplierMatch.product_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def _batch_get_statuses(
        self, ids: list[int], report_date: date
    ) -> dict[int, RecommendationStatus]:
        """批量取审核状态。"""
        if not ids:
            return {}
        stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id.in_(ids),
            RecommendationStatus.report_date == report_date,
        )
        result = await self._session.execute(stmt)
        return {r.product_id: r for r in result.scalars().all()}

    @staticmethod
    def _extract_action(reasons_json: str | None) -> str:
        """从 reasons JSON 中提取 action。"""
        if not reasons_json:
            return "WATCH"
        import json

        try:
            reasons = json.loads(reasons_json)
        except (json.JSONDecodeError, TypeError):
            return "WATCH"
        if isinstance(reasons, list) and reasons:
            first = reasons[0]
            if isinstance(first, str):
                return first
        return "WATCH"
