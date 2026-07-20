"""Scoring optimizer — learn from recommendation reviews to improve scoring weights."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.review_repository import ReviewRepository
from app.database.scoring_repository import ScoringRepository
from app.models.recommendation_review import RecommendationReview
from app.models.scoring_config import DEFAULT_WEIGHTS


# ── Weight dimension → review metric mapping ─────────────

_WEIGHT_DIMENSIONS = [
    "sales_weight",
    "trend_weight",
    "viewer_weight",
    "price_weight",
    "competition_weight",
]

# How much to adjust per optimization cycle
_ADJUST_STEP = 0.05
_MIN_WEIGHT = 0.05
_MAX_WEIGHT = 0.50


class ScoringOptimizer:
    """评分权重自动优化器。

    根据推荐复盘结果自动调整评分权重：
      - 成功商品的共性特征 → 提高对应权重
      - 失败商品的共性特征 → 降低对应权重

    权重总和始终保持 1.0（100%）。

    Usage::

        optimizer = ScoringOptimizer(session)
        result = await optimizer.optimize()
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._review_repo = ReviewRepository(session)
        self._scoring_repo = ScoringRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def optimize(self) -> dict[str, Any]:
        """执行一轮权重优化。

        Returns:
            {
                "old_version": int,
                "new_version": int,
                "changes": dict[str, str],
                "reason": str,
            }
        """
        # 获取当前配置
        current = await self._scoring_repo.get_active()
        old_version = current.version if current else 0
        current_weights = current.to_weights_dict() if current else dict(DEFAULT_WEIGHTS)

        # 获取最近复盘数据
        reviews = await self._review_repo.get_reviews(limit=100)
        if not reviews:
            logger.info("[Optimizer] 无复盘数据，跳过优化")
            return {
                "old_version": old_version,
                "new_version": old_version,
                "changes": {},
                "reason": "无复盘数据",
            }

        # 分析成功/失败商品的特征分布
        analysis = self._analyze_reviews(reviews)

        # 计算新权重
        new_weights = self._adjust_weights(current_weights, analysis)

        # 保存新配置
        new_config = await self._scoring_repo.update_weights(new_weights)
        try:
            await self._session.commit()
        except Exception as e:
            logger.warning("[Optimizer] 保存权重失败: {}", e)

        # 计算变化描述
        changes = self._describe_changes(current_weights, new_weights)
        reason = self._generate_reason(analysis)

        result = {
            "old_version": old_version,
            "new_version": new_config.version,
            "changes": changes,
            "reason": reason,
        }

        logger.info(
            "[Optimizer] v{} → v{}, changes={}",
            old_version, new_config.version, changes,
        )
        return result

    # ── Analysis ──────────────────────────────────────────────

    @staticmethod
    def _calc_contribution(
        success_avg: float | None,
        failed_avg: float | None,
    ) -> float:
        """计算单个维度的贡献值 (-1 ~ 1)。

        处理缺失数据：
          - 两组都无 → 0
          - 仅成功组 → 正值（成功商品表现好）
          - 仅失败组 → 负值（失败商品表现差）
          - 两组都有 → 归一化差值
        """
        if success_avg is None and failed_avg is None:
            return 0.0
        if success_avg is not None and failed_avg is None:
            # 只有成功数据，正方向
            denom = max(abs(success_avg), 1.0)
            return max(-1.0, min(1.0, success_avg / denom))
        if success_avg is None and failed_avg is not None:
            # 只有失败数据，负方向
            denom = max(abs(failed_avg), 1.0)
            return max(-1.0, min(1.0, failed_avg / denom))

        # 两组都有数据
        diff = success_avg - failed_avg  # type: ignore[operator]
        denom = max(abs(success_avg), abs(failed_avg), 1.0)  # type: ignore[arg-type]
        return max(-1.0, min(1.0, diff / denom))

    @staticmethod
    def _analyze_reviews(reviews: list[RecommendationReview] | Any) -> dict[str, float]:
        """分析复盘数据中成功/失败商品的特征模式。

        Returns:
            {"sales_contribution": float, "trend_contribution": float, ...}
            每个值为 -1.0 ~ 1.0，正表示成功商品该特征强，负表示失败商品该特征强。
        """
        success_reviews = [r for r in reviews if r.result == "SUCCESS"]
        failed_reviews = [r for r in reviews if r.result == "FAILED"]

        if not success_reviews and not failed_reviews:
            return {dim: 0.0 for dim in _WEIGHT_DIMENSIONS}

        # 计算成功和失败商品的平均 sales_change 和 trend_change
        success_sales = (
            sum(r.sales_change for r in success_reviews) / len(success_reviews)
            if success_reviews else None
        )
        failed_sales = (
            sum(r.sales_change for r in failed_reviews) / len(failed_reviews)
            if failed_reviews else None
        )
        success_trend = (
            sum(r.trend_change for r in success_reviews) / len(success_reviews)
            if success_reviews else None
        )
        failed_trend = (
            sum(r.trend_change for r in failed_reviews) / len(failed_reviews)
            if failed_reviews else None
        )

        # 计算归一化贡献值 (-1 ~ 1)
        sales_contribution = ScoringOptimizer._calc_contribution(success_sales, failed_sales)
        trend_contribution = ScoringOptimizer._calc_contribution(success_trend, failed_trend)

        # viewer 和 price 暂使用 trend 作为代理
        viewer_contribution = trend_contribution * 0.5
        price_contribution = sales_contribution * 0.3
        competition_contribution = trend_contribution * 0.4

        return {
            "sales_weight": round(sales_contribution, 3),
            "trend_weight": round(trend_contribution, 3),
            "viewer_weight": round(viewer_contribution, 3),
            "price_weight": round(price_contribution, 3),
            "competition_weight": round(competition_contribution, 3),
        }

    # ── Weight adjustment ─────────────────────────────────────

    @staticmethod
    def _adjust_weights(
        current: dict[str, float],
        analysis: dict[str, float],
    ) -> dict[str, float]:
        """根据分析结果调整权重，保持总和为 1.0。"""
        new_weights: dict[str, float] = {}

        for dim in _WEIGHT_DIMENSIONS:
            contribution = analysis.get(dim, 0.0)
            adjustment = contribution * _ADJUST_STEP

            old_val = current.get(dim, 1.0 / len(_WEIGHT_DIMENSIONS))
            new_val = old_val + adjustment

            # 限制范围
            new_val = max(_MIN_WEIGHT, min(_MAX_WEIGHT, new_val))
            new_weights[dim] = round(new_val, 4)

        # 归一化使总和为 1.0
        total = sum(new_weights.values())
        if total > 0:
            for dim in new_weights:
                new_weights[dim] = round(new_weights[dim] / total, 4)

        return new_weights

    # ── Change description ────────────────────────────────────

    @staticmethod
    def _describe_changes(old: dict[str, float], new: dict[str, float]) -> dict[str, str]:
        """生成权重变化描述。"""
        changes: dict[str, str] = {}
        for dim in _WEIGHT_DIMENSIONS:
            old_val = old.get(dim, 0.0)
            new_val = new.get(dim, 0.0)
            diff = new_val - old_val
            if abs(diff) < 0.001:
                changes[dim] = "0%"
            elif diff > 0:
                changes[dim] = f"+{diff * 100:.1f}%"
            else:
                changes[dim] = f"{diff * 100:.1f}%"
        return changes

    @staticmethod
    def _generate_reason(analysis: dict[str, float]) -> str:
        """根据分析结果生成优化原因。"""
        if not analysis:
            return "无足够数据"

        # 找出贡献最大的维度
        max_dim = max(analysis, key=lambda k: abs(analysis[k]))
        max_val = analysis[max_dim]

        dim_names = {
            "sales_weight": "销量",
            "trend_weight": "趋势",
            "viewer_weight": "浏览热度",
            "price_weight": "价格",
            "competition_weight": "竞争度",
        }

        name = dim_names.get(max_dim, max_dim)
        if max_val > 0.1:
            return f"{name}因素对成功推荐贡献最高，已提高权重"
        elif max_val < -0.1:
            return f"{name}因素与成功推荐负相关，已降低权重"
        else:
            return "各因素贡献均衡，微调权重"
