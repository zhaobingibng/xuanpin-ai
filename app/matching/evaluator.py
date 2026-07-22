"""MatchingEvaluator — 商品匹配评估系统。

评估淘宝商品标题到1688供应商商品的匹配质量。
支持 Top-1/3/10 准确率和平均分数计算。

Usage:
    evaluator = MatchingEvaluator()
    result = await evaluator.evaluate(products, ground_truth, matcher_fn)
    # result = {
    #     "total_count": 10,
    #     "top1_accuracy": 0.6,
    #     "top3_accuracy": 0.8,
    #     "top10_accuracy": 0.95,
    #     "avg_score": 0.72,
    #     "details": [...],
    # }
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Sequence


# matcher_fn signature: async (title: str, top_k: int) -> list[dict]
# Each result dict must contain at least: {"supplier_product_id": ..., "final_score": ...}
MatcherFn = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


class MatchingEvaluator:
    """评估商品匹配质量。

    对每个查询商品，使用 matcher_fn 获取 top-k 匹配结果，
    与 ground_truth 对比计算准确率指标。

    Usage:
        evaluator = MatchingEvaluator()
        result = await evaluator.evaluate(
            products=[
                {"id": "t1", "title": "坚果礼盒"},
                {"id": "t2", "title": "蓝牙耳机"},
            ],
            ground_truth={
                "t1": "p1",  # product t1 should match supplier p1
                "t2": "p3",  # product t2 should match supplier p3
            },
            matcher_fn=async_matcher,
        )
    """

    def __init__(self) -> None:
        pass

    # ── Public API ────────────────────────────────────────────

    async def evaluate(
        self,
        products: Sequence[dict[str, Any]],
        ground_truth: dict[str, str],
        matcher_fn: MatcherFn,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Evaluate matching quality.

        Args:
            products: List of query products, each with "id" and "title".
            ground_truth: Mapping from product_id → correct supplier_product_id.
            matcher_fn: Async function (title, top_k) → list[result_dict].
            top_k: Number of top results to consider.

        Returns:
            Dict with total_count, top1_accuracy, top3_accuracy,
            top10_accuracy, avg_score, details.
        """
        if not products:
            return self._empty_result()

        details: list[dict[str, Any]] = []
        correct_in_top1 = 0
        correct_in_top3 = 0
        correct_in_top10 = 0
        total_score = 0.0
        score_count = 0

        matched_count = 0  # products that have a ground truth entry

        for product in products:
            pid = product.get("id", "")
            title = product.get("title", "")
            expected_supplier_id = ground_truth.get(pid, "")

            # Call matcher
            results = await matcher_fn(title, top_k)

            # Find the correct match in results
            found_rank: int | None = None
            found_score: float = 0.0
            for rank, r in enumerate(results):
                supplier_id = str(r.get("supplier_product_id", ""))
                if expected_supplier_id and supplier_id == expected_supplier_id:
                    found_rank = rank + 1  # 1-based
                    found_score = float(r.get("final_score", 0))
                    break

            # Update counters (only if ground truth exists)
            if expected_supplier_id:
                matched_count += 1
                if found_rank is not None:
                    if found_rank <= 1:
                        correct_in_top1 += 1
                    if found_rank <= 3:
                        correct_in_top3 += 1
                    if found_rank <= top_k:
                        correct_in_top10 += 1

                # Record score (0 if not found)
                if found_rank is not None:
                    total_score += found_score
                    score_count += 1
                else:
                    score_count += 1  # score 0 for not found

            details.append({
                "product_id": pid,
                "title": title,
                "expected_supplier_id": expected_supplier_id,
                "found_rank": found_rank,
                "found_score": round(found_score, 4),
                "match_hit": found_rank is not None,
                "top_results": [
                    {
                        "supplier_product_id": str(r.get("supplier_product_id", "")),
                        "score": round(float(r.get("final_score", 0)), 4),
                    }
                    for r in results[:5]
                ],
            })

        # Calculate metrics
        if matched_count == 0:
            return {
                "total_count": 0,
                "matched_count": 0,
                "top1_accuracy": 0.0,
                "top3_accuracy": 0.0,
                "top10_accuracy": 0.0,
                "avg_score": 0.0,
                "details": details,
            }

        return {
            "total_count": len(products),
            "matched_count": matched_count,
            "top1_accuracy": round(correct_in_top1 / matched_count, 4),
            "top3_accuracy": round(correct_in_top3 / matched_count, 4),
            "top10_accuracy": round(correct_in_top10 / matched_count, 4),
            "avg_score": round(total_score / score_count, 4) if score_count > 0 else 0.0,
            "details": details,
        }

    # ── Sync helper (for sync matcher wrappers) ──────────────

    def evaluate_sync(
        self,
        products: Sequence[dict[str, Any]],
        ground_truth: dict[str, str],
        results_map: dict[str, list[dict[str, Any]]],
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Evaluate using pre-computed results (synchronous).

        Useful for testing when matcher results are pre-computed
        or mocked.

        Args:
            products: Query products.
            ground_truth: product_id → correct supplier_product_id.
            results_map: product_id → list[result_dict] (pre-computed).
            top_k: Top-k to consider.

        Returns:
            Evaluation result dict.
        """
        if not products:
            return self._empty_result()

        details: list[dict[str, Any]] = []
        correct_in_top1 = 0
        correct_in_top3 = 0
        correct_in_top10 = 0
        total_score = 0.0
        score_count = 0
        matched_count = 0

        for product in products:
            pid = product.get("id", "")
            title = product.get("title", "")
            expected_supplier_id = ground_truth.get(pid, "")
            results = results_map.get(pid, [])[:top_k]

            found_rank: int | None = None
            found_score: float = 0.0
            for rank, r in enumerate(results):
                supplier_id = str(r.get("supplier_product_id", ""))
                if expected_supplier_id and supplier_id == expected_supplier_id:
                    found_rank = rank + 1
                    found_score = float(r.get("final_score", 0))
                    break

            if expected_supplier_id:
                matched_count += 1
                if found_rank is not None:
                    if found_rank <= 1:
                        correct_in_top1 += 1
                    if found_rank <= 3:
                        correct_in_top3 += 1
                    if found_rank <= top_k:
                        correct_in_top10 += 1

                if found_rank is not None:
                    total_score += found_score
                    score_count += 1
                else:
                    score_count += 1

            details.append({
                "product_id": pid,
                "title": title,
                "expected_supplier_id": expected_supplier_id,
                "found_rank": found_rank,
                "found_score": round(found_score, 4),
                "match_hit": found_rank is not None,
            })

        if matched_count == 0:
            return {
                "total_count": 0,
                "matched_count": 0,
                "top1_accuracy": 0.0,
                "top3_accuracy": 0.0,
                "top10_accuracy": 0.0,
                "avg_score": 0.0,
                "details": details,
            }

        return {
            "total_count": len(products),
            "matched_count": matched_count,
            "top1_accuracy": round(correct_in_top1 / matched_count, 4),
            "top3_accuracy": round(correct_in_top3 / matched_count, 4),
            "top10_accuracy": round(correct_in_top10 / matched_count, 4),
            "avg_score": round(total_score / score_count, 4) if score_count > 0 else 0.0,
            "details": details,
        }

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "total_count": 0,
            "matched_count": 0,
            "top1_accuracy": 0.0,
            "top3_accuracy": 0.0,
            "top10_accuracy": 0.0,
            "avg_score": 0.0,
            "details": [],
        }
