"""EvaluationReport — 真实商品匹配效果评估报告生成器。

使用 ProductMatcher 对真实数据进行匹配，输出准确率 + 利润空间报告。

评估数据格式 (JSON):
[
    {
        "title": "三只松鼠坚果礼盒装",
        "price": 99.0,
        "correct_supplier_product_id": 1,
        "notes": "人工标注：应匹配坚果礼盒类商品"
    }
]

Usage:
    report_gen = EvaluationReport()
    report = await report_gen.generate(session, eval_data, top_k=10)
    # report = {
    #     "summary": {
    #         "total": 10,
    #         "top1_accuracy": 0.6,
    #         "top3_accuracy": 0.8,
    #         "top10_recall": 0.95,
    #         "avg_final_score": 0.72,
    #         "avg_profit_margin": 45.3,
    #     },
    #     "details": [...],
    #     "profit_distribution": {...},
    # }
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


# ── Helper ────────────────────────────────────────────────────

def _calc_profit_margin(sell_price: float, cost_price: float) -> float:
    """Calculate profit margin percentage."""
    if sell_price <= 0:
        return 0.0
    return round((sell_price - cost_price) / sell_price * 100, 1)


# ── Report Generator ──────────────────────────────────────────

class EvaluationReport:
    """真实商品匹配评估报告生成器。

    使用 ProductMatcher 评估匹配准确率 + 利润空间。

    Usage::

        report_gen = EvaluationReport()
        report = await report_gen.generate(session, eval_data, top_k=10)
        print(report["summary"]["top3_accuracy"])
    """

    def __init__(self) -> None:
        pass

    # ── Main API ──────────────────────────────────────────────

    async def generate(
        self,
        session: AsyncSession,
        evaluation_data: list[dict[str, Any]],
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run evaluation and produce a structured report.

        Args:
            session: 异步数据库会话（用于 ProductMatcher）。
            evaluation_data: 人工标注的评估数据列表，每项包含:
                - title: str — 淘宝商品标题
                - price: float — 淘宝售价
                - correct_supplier_product_id: int — 正确的1688商品ID
                - notes: str (可选) — 标注备注
            top_k: ProductMatcher 搜索深度。

        Returns:
            评估报告字典，包含 summary / details / profit_distribution。
        """
        if not evaluation_data:
            return self._empty_report()

        # Lazy import — avoid circular dependency at module level
        from app.matching.product_matcher import ProductMatcher

        matcher = ProductMatcher(session)

        details: list[dict[str, Any]] = []
        top1_hits = 0
        top3_hits = 0
        top10_hits = 0
        total_final_score = 0.0
        score_count = 0
        total_profit_margin = 0.0
        profit_count = 0
        labeled_count = 0

        for item in evaluation_data:
            title = str(item.get("title", ""))
            sell_price = float(item.get("price", 0))
            correct_id = item.get("correct_supplier_product_id")
            notes = item.get("notes", "")

            if not title:
                continue

            # Call ProductMatcher
            try:
                results = await matcher.match_product(title, top_k=top_k)
            except Exception as exc:
                logger.warning(
                    "[EvaluationReport] match_product failed for '{}': {}",
                    title[:30], exc,
                )
                results = []

            # Find correct match
            found_rank: int | None = None
            found_score: float = 0.0
            found_price: float = 0.0
            top_items: list[dict[str, Any]] = []

            for rank, r in enumerate(results[:top_k]):
                sp_id = r.get("supplier_product_id")
                score = float(r.get("final_score", 0))
                price = float(r.get("price", 0))

                top_items.append({
                    "rank": rank + 1,
                    "supplier_product_id": sp_id,
                    "title": str(r.get("title", ""))[:60],
                    "final_score": round(score, 4),
                    "price": price,
                    "profit_margin": _calc_profit_margin(sell_price, price),
                })

                if correct_id is not None and sp_id == correct_id:
                    found_rank = rank + 1
                    found_score = score
                    found_price = price

            # Update counters
            if correct_id is not None:
                labeled_count += 1
                if found_rank is not None:
                    if found_rank <= 1:
                        top1_hits += 1
                    if found_rank <= 3:
                        top3_hits += 1
                    if found_rank <= top_k:
                        top10_hits += 1
                    total_final_score += found_score
                    score_count += 1

                    # Profit margin for the correctly matched item
                    margin = _calc_profit_margin(sell_price, found_price)
                    total_profit_margin += margin
                    profit_count += 1
                else:
                    score_count += 1  # miss contributes 0 to avg score

            # Record detail
            details.append({
                "title": title,
                "price": sell_price,
                "correct_supplier_product_id": correct_id,
                "notes": notes,
                "found_rank": found_rank,
                "found_score": round(found_score, 4),
                "found_price": found_price,
                "match_hit": found_rank is not None,
                "top_items": top_items[:5],
            })

        # ── Build summary ──────────────────────────────────────
        summary = {
            "total": len(details),
            "labeled_count": labeled_count,
            "top1_accuracy": round(top1_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "top3_accuracy": round(top3_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "top10_recall": round(top10_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "avg_final_score": round(total_final_score / score_count, 4) if score_count > 0 else 0.0,
            "avg_profit_margin": round(total_profit_margin / profit_count, 1) if profit_count > 0 else 0.0,
        }

        # ── Profit distribution ────────────────────────────────
        profit_buckets = {"<0%": 0, "0-20%": 0, "20-40%": 0, "40-60%": 0, ">60%": 0}
        for d in details:
            if d["match_hit"] and d.get("found_price", 0) > 0:
                margin = _calc_profit_margin(d["price"], d["found_price"])
                if margin < 0:
                    profit_buckets["<0%"] += 1
                elif margin < 20:
                    profit_buckets["0-20%"] += 1
                elif margin < 40:
                    profit_buckets["20-40%"] += 1
                elif margin < 60:
                    profit_buckets["40-60%"] += 1
                else:
                    profit_buckets[">60%"] += 1

        # ── Missed cases ───────────────────────────────────────
        missed = [
            d for d in details
            if d["correct_supplier_product_id"] is not None and not d["match_hit"]
        ]

        # ── Log ────────────────────────────────────────────────
        logger.info(
            "[EvaluationReport] 评估完成: total={}, labeled={}, "
            "top1={:.1%}, top3={:.1%}, top10={:.1%}, "
            "avg_score={:.3f}, avg_margin={:.1f}%, missed={}",
            summary["total"], summary["labeled_count"],
            summary["top1_accuracy"], summary["top3_accuracy"],
            summary["top10_recall"],
            summary["avg_final_score"], summary["avg_profit_margin"],
            len(missed),
        )

        return {
            "summary": summary,
            "details": details,
            "profit_distribution": profit_buckets,
            "missed_count": len(missed),
            "missed_cases": missed,
        }

    # ── Sync helper for testing ───────────────────────────────

    def generate_sync(
        self,
        evaluation_data: list[dict[str, Any]],
        results_map: dict[str, list[dict[str, Any]]],
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Generate report using pre-computed matcher results (sync).

        Args:
            evaluation_data: 人工标注的评估数据。
            results_map: 预计算匹配结果，key=title, value=list[result_dict]。
            top_k: 搜索深度。

        Returns:
            评估报告字典。
        """
        if not evaluation_data:
            return self._empty_report()

        details: list[dict[str, Any]] = []
        top1_hits = 0
        top3_hits = 0
        top10_hits = 0
        total_final_score = 0.0
        score_count = 0
        total_profit_margin = 0.0
        profit_count = 0
        labeled_count = 0

        for item in evaluation_data:
            title = str(item.get("title", ""))
            sell_price = float(item.get("price", 0))
            correct_id = item.get("correct_supplier_product_id")
            notes = item.get("notes", "")

            if not title:
                continue

            results = results_map.get(title, [])[:top_k]

            found_rank: int | None = None
            found_score: float = 0.0
            found_price: float = 0.0
            top_items: list[dict[str, Any]] = []

            for rank, r in enumerate(results):
                sp_id = r.get("supplier_product_id")
                score = float(r.get("final_score", 0))
                price = float(r.get("price", 0))

                top_items.append({
                    "rank": rank + 1,
                    "supplier_product_id": sp_id,
                    "title": str(r.get("title", ""))[:60],
                    "final_score": round(score, 4),
                    "price": price,
                    "profit_margin": _calc_profit_margin(sell_price, price),
                })

                if correct_id is not None and sp_id == correct_id:
                    found_rank = rank + 1
                    found_score = score
                    found_price = price

            if correct_id is not None:
                labeled_count += 1
                if found_rank is not None:
                    if found_rank <= 1:
                        top1_hits += 1
                    if found_rank <= 3:
                        top3_hits += 1
                    if found_rank <= top_k:
                        top10_hits += 1
                    total_final_score += found_score
                    score_count += 1
                    margin = _calc_profit_margin(sell_price, found_price)
                    total_profit_margin += margin
                    profit_count += 1
                else:
                    score_count += 1

            details.append({
                "title": title,
                "price": sell_price,
                "correct_supplier_product_id": correct_id,
                "notes": notes,
                "found_rank": found_rank,
                "found_score": round(found_score, 4),
                "found_price": found_price,
                "match_hit": found_rank is not None,
                "top_items": top_items[:5],
            })

        summary = {
            "total": len(details),
            "labeled_count": labeled_count,
            "top1_accuracy": round(top1_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "top3_accuracy": round(top3_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "top10_recall": round(top10_hits / labeled_count, 4) if labeled_count > 0 else 0.0,
            "avg_final_score": round(total_final_score / score_count, 4) if score_count > 0 else 0.0,
            "avg_profit_margin": round(total_profit_margin / profit_count, 1) if profit_count > 0 else 0.0,
        }

        profit_buckets = {"<0%": 0, "0-20%": 0, "20-40%": 0, "40-60%": 0, ">60%": 0}
        for d in details:
            if d["match_hit"] and d.get("found_price", 0) > 0:
                margin = _calc_profit_margin(d["price"], d["found_price"])
                if margin < 0:
                    profit_buckets["<0%"] += 1
                elif margin < 20:
                    profit_buckets["0-20%"] += 1
                elif margin < 40:
                    profit_buckets["20-40%"] += 1
                elif margin < 60:
                    profit_buckets["40-60%"] += 1
                else:
                    profit_buckets[">60%"] += 1

        missed = [
            d for d in details
            if d["correct_supplier_product_id"] is not None and not d["match_hit"]
        ]

        return {
            "summary": summary,
            "details": details,
            "profit_distribution": profit_buckets,
            "missed_count": len(missed),
            "missed_cases": missed,
        }

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _empty_report() -> dict[str, Any]:
        return {
            "summary": {
                "total": 0,
                "labeled_count": 0,
                "top1_accuracy": 0.0,
                "top3_accuracy": 0.0,
                "top10_recall": 0.0,
                "avg_final_score": 0.0,
                "avg_profit_margin": 0.0,
            },
            "details": [],
            "profit_distribution": {"<0%": 0, "0-20%": 0, "20-40%": 0, "40-60%": 0, ">60%": 0},
            "missed_count": 0,
            "missed_cases": [],
        }
