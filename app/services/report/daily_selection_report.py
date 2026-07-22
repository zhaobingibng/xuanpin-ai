"""DailySelectionReportService — comprehensive daily selection report.

Aggregates data from multiple sources:
- New product detection
- Supply chain matching results
- Profit analysis
- AI recommendations

Outputs structured JSON report, integrates with existing DailyReport system.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.supply_chain_match import SupplyChainMatch


class DailySelectionReportService:
    """综合选品日报服务。

    整合多源数据生成结构化日报 JSON：
    - 新发现商品（NewProductDetector）
    - 供应链匹配结果（SupplyChainMatcher）
    - 利润分析（ProfitCalculator）
    - AI 推荐（SupplyChainReportGenerator）

    不新增数据库表，复用现有 DailyReport 存储。

    Usage::

        svc = DailySelectionReportService(session)
        report = await svc.generate()
        # report = {
        #   "date": "2026-07-21",
        #   "summary": {...},
        #   "new_products": [...],
        #   "supply_chain_matches": [...],
        #   "profit_analysis": {...},
        #   "ai_recommendations": [...],
        #   "top_picks": [...]
        # }
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate(
        self,
        platforms: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """生成综合选品日报。

        Args:
            platforms: 目标平台列表，None 表示全部。
            limit: 每类数据上限。

        Returns:
            结构化日报 JSON。
        """
        report_date = date.today().isoformat()
        logger.info("[DailySelectionReport] 开始生成日报: {}", report_date)

        # 1. 新发现商品
        new_products = await self._collect_new_products(limit=limit)

        # 2. 供应链匹配结果
        sc_matches = await self._collect_supply_chain_matches(limit=limit)

        # 3. 利润分析
        profit_analysis = self._analyze_profits(sc_matches)

        # 4. AI 推荐
        ai_recommendations = await self._generate_ai_recommendations(
            new_products, sc_matches, limit=limit
        )

        # 5. TOP 精选
        top_picks = self._select_top_picks(
            new_products, sc_matches, ai_recommendations, limit=min(limit, 10)
        )

        # 6. 汇总统计
        summary = self._build_summary(new_products, sc_matches, profit_analysis)

        report = {
            "date": report_date,
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "new_products": new_products,
            "supply_chain_matches": sc_matches,
            "profit_analysis": profit_analysis,
            "ai_recommendations": ai_recommendations,
            "top_picks": top_picks,
        }

        logger.info(
            "[DailySelectionReport] 日报生成完成: date={}, new={}, matched={}, top={}",
            report_date, len(new_products), len(sc_matches), len(top_picks),
        )
        return report

    # ── Data Collection ──────────────────────────────────────

    async def _collect_new_products(self, limit: int = 20) -> list[dict[str, Any]]:
        """收集新发现商品。"""
        try:
            # 查询最近 24h 内入库的商品
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=1)

            stmt = (
                select(Product)
                .where(Product.created_at >= cutoff)
                .order_by(Product.ai_score.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            products = result.scalars().all()

            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "platform": p.platform,
                    "shop": p.shop,
                    "price": p.price,
                    "ai_score": p.ai_score or 0,
                    "image": p.image or "",
                }
                for p in products
            ]
        except Exception as e:
            logger.warning("[DailySelectionReport] 收集新商品失败: {}", e)
            return []

    async def _collect_supply_chain_matches(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """收集供应链匹配结果。"""
        try:
            stmt = (
                select(SupplyChainMatch)
                .where(SupplyChainMatch.status == "MATCHED")
                .order_by(SupplyChainMatch.match_score.desc())
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            matches = result.scalars().all()

            items = []
            for m in matches:
                # 获取关联商品信息
                product = await self._session.get(Product, m.product_id)
                items.append({
                    "match_id": m.id,
                    "product_id": m.product_id,
                    "product_name": product.name if product else "",
                    "match_score": m.match_score,
                    "match_type": m.match_type or "title",
                    "cost_price": m.cost_price,
                    "sell_price": m.sell_price,
                    "profit_margin": m.profit_margin,
                    "profit_amount": m.profit_amount,
                    "status": m.status,
                })
            return items
        except Exception as e:
            logger.warning("[DailySelectionReport] 收集匹配结果失败: {}", e)
            return []

    def _analyze_profits(
        self, matches: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """分析利润数据。"""
        if not matches:
            return {
                "total_matches": 0,
                "avg_margin": 0.0,
                "max_margin": 0.0,
                "min_margin": 0.0,
                "high_profit_count": 0,  # margin >= 30%
                "medium_profit_count": 0,  # 15% <= margin < 30%
                "low_profit_count": 0,  # 0 <= margin < 15%
                "negative_profit_count": 0,  # margin < 0
            }

        margins = [m["profit_margin"] for m in matches]
        return {
            "total_matches": len(matches),
            "avg_margin": round(sum(margins) / len(margins), 2),
            "max_margin": round(max(margins), 2),
            "min_margin": round(min(margins), 2),
            "high_profit_count": sum(1 for m in margins if m >= 30),
            "medium_profit_count": sum(1 for m in margins if 15 <= m < 30),
            "low_profit_count": sum(1 for m in margins if 0 <= m < 15),
            "negative_profit_count": sum(1 for m in margins if m < 0),
        }

    async def _generate_ai_recommendations(
        self,
        new_products: list[dict[str, Any]],
        sc_matches: list[dict[str, Any]],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """生成 AI 推荐（基于规则，LLM 可选增强）。"""
        recommendations: list[dict[str, Any]] = []

        # 高利润商品推荐
        for match in sc_matches:
            if match["profit_margin"] >= 30:
                recommendations.append({
                    "product_id": match["product_id"],
                    "product_name": match["product_name"],
                    "reason": "high_profit",
                    "score": match["profit_margin"],
                    "action": "SELL" if match["profit_margin"] >= 40 else "TEST",
                    "detail": f"利润率 {match['profit_margin']:.1f}%",
                })

        # 新发现高分商品推荐
        for product in new_products:
            if product["ai_score"] >= 70:
                # 避免重复推荐
                if any(r["product_id"] == product["id"] for r in recommendations):
                    continue
                recommendations.append({
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "reason": "high_score_new",
                    "score": product["ai_score"],
                    "action": "TEST",
                    "detail": f"新发现商品，AI评分 {product['ai_score']}",
                })

        # 按 score 排序，取 top N
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:limit]

    def _select_top_picks(
        self,
        new_products: list[dict[str, Any]],
        sc_matches: list[dict[str, Any]],
        ai_recommendations: list[dict[str, Any]],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """选出 TOP 精选商品。"""
        # 优先选择有 AI 推荐且有供应链匹配的商品
        recommended_ids = {r["product_id"] for r in ai_recommendations}
        matched_ids = {m["product_id"] for m in sc_matches}

        top_picks: list[dict[str, Any]] = []

        # 1. 有推荐 + 有匹配 = 最佳选择
        for match in sc_matches:
            if match["product_id"] in recommended_ids and match["profit_margin"] >= 20:
                top_picks.append({
                    "product_id": match["product_id"],
                    "product_name": match["product_name"],
                    "selection_reason": "recommended+matched",
                    "profit_margin": match["profit_margin"],
                    "match_score": match["match_score"],
                })

        # 2. 仅有匹配但利润高
        for match in sc_matches:
            if match["product_id"] not in recommended_ids and match["profit_margin"] >= 35:
                if len(top_picks) >= limit:
                    break
                top_picks.append({
                    "product_id": match["product_id"],
                    "product_name": match["product_name"],
                    "selection_reason": "high_profit",
                    "profit_margin": match["profit_margin"],
                    "match_score": match["match_score"],
                })

        # 3. 仅有推荐（新高分商品）
        for rec in ai_recommendations:
            if rec["product_id"] not in matched_ids:
                if len(top_picks) >= limit:
                    break
                top_picks.append({
                    "product_id": rec["product_id"],
                    "product_name": rec["product_name"],
                    "selection_reason": rec["reason"],
                    "profit_margin": None,
                    "match_score": None,
                })

        return top_picks[:limit]

    def _build_summary(
        self,
        new_products: list[dict[str, Any]],
        sc_matches: list[dict[str, Any]],
        profit_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """构建汇总统计。"""
        return {
            "new_products_count": len(new_products),
            "matched_count": len(sc_matches),
            "avg_profit_margin": profit_analysis["avg_margin"],
            "high_profit_count": profit_analysis["high_profit_count"],
            "recommendation_count": (
                profit_analysis["high_profit_count"]
                + profit_analysis["medium_profit_count"]
            ),
        }
