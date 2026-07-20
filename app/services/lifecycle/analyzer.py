"""Lifecycle analyzer — determine product lifecycle stage from history trends."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.history_repository import HistoryRepository
from app.models.product_history import ProductHistory


class LifecycleAnalyzer:
    """Analyze product lifecycle stage based on historical data.

    Stages:
      - NEW:      Few records or recently appeared (< 7 days)
      - RISING:   Sales or viewers growing > 30%
      - HOT:      3+ records, steady growth, score >= 80
      - DECLINE:  Sales or viewers declining > 30%

    Usage::

        analyzer = LifecycleAnalyzer(session)
        result = await analyzer.analyze(product_id=1)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._history_repo = HistoryRepository(session)

    async def analyze(self, product_id: int) -> dict[str, Any]:
        """Analyze lifecycle stage for a product.

        Args:
            product_id: The product to analyze.

        Returns:
            Dict with product_id, stage, score, signals.
        """
        history = list(await self._history_repo.get_history(product_id, limit=30))

        # Filter to last 7 days
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent = [h for h in history if h.record_time >= cutoff]
        recent.sort(key=lambda h: h.record_time)

        stage, signals = self._determine_stage(recent)
        score = self._calculate_lifecycle_score(recent, stage)

        result = {
            "product_id": product_id,
            "stage": stage,
            "score": score,
            "signals": signals,
        }

        logger.debug(
            "[Lifecycle] product_id={}, stage={}, score={}",
            product_id, stage, score,
        )
        return result

    # ── Stage detection ────────────────────────────────────────

    def _determine_stage(
        self, history: list[ProductHistory]
    ) -> tuple[str, list[str]]:
        """Determine lifecycle stage from sorted history records.

        Returns:
            (stage, signals) tuple.
        """
        if len(history) <= 2:
            return "NEW", ["新品出现"]

        # Check if first appearance is within 7 days
        first_record = history[0]
        days_since_first = (datetime.utcnow() - first_record.record_time).days
        if days_since_first < 7:
            return "NEW", ["新品出现"]

        # Calculate growth rates (first → last)
        sales_growth = self._calculate_growth_rate(
            history[0].sales_24h, history[-1].sales_24h
        )
        viewers_growth = self._calculate_growth_rate(
            history[0].viewers, history[-1].viewers
        )

        # DECLINE: sales or viewers dropped > 30%
        if sales_growth < -30 or viewers_growth < -30:
            signals: list[str] = []
            if sales_growth < -30:
                signals.append("销量下降")
            if viewers_growth < -30:
                signals.append("热度降低")
            return "DECLINE", signals

        # HOT: 3+ records AND steady growth AND score >= 80
        if len(history) >= 3:
            # Check steady growth: each consecutive pair shows non-negative growth
            steady = self._is_steady_growth(history)
            if steady and (sales_growth > 0 or viewers_growth > 0):
                # Use a simple scoring heuristic for lifecycle score
                avg_score = self._estimate_score(history)
                if avg_score >= 80:
                    signals = ["持续热门", "高评分"]
                    return "HOT", signals

        # RISING: sales or viewers growing > 30%
        if sales_growth > 30 or viewers_growth > 30:
            signals = []
            if sales_growth > 30:
                signals.append("销量快速增长")
            if viewers_growth > 30:
                signals.append("浏览上涨")
            return "RISING", signals

        # Default to NEW for ambiguous cases
        return "NEW", ["新品出现"]

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _calculate_growth_rate(old: int, new: int) -> float:
        """Calculate percentage growth rate."""
        if old == 0:
            return 100.0 if new > 0 else 0.0
        return ((new - old) / old) * 100.0

    @staticmethod
    def _is_steady_growth(history: list[ProductHistory]) -> bool:
        """Check if sales show non-negative consecutive growth."""
        for i in range(1, len(history)):
            if history[i].sales_24h < history[i - 1].sales_24h:
                return False
        return True

    @staticmethod
    def _estimate_score(history: list[ProductHistory]) -> float:
        """Estimate a score from recent history (simplified)."""
        if not history:
            return 0.0
        latest = history[-1]
        score = 0.0
        # Sales contribution (up to 40)
        if latest.sales_24h >= 5000:
            score += 40
        elif latest.sales_24h >= 1000:
            score += 30
        elif latest.sales_24h >= 100:
            score += 20
        else:
            score += 10
        # Viewers contribution (up to 30)
        if latest.viewers >= 10000:
            score += 30
        elif latest.viewers >= 1000:
            score += 20
        else:
            score += 10
        # AI score (up to 30)
        if latest.ai_score is not None:
            score += min(latest.ai_score * 0.3, 30)
        return score

    def _calculate_lifecycle_score(
        self, history: list[ProductHistory], stage: str
    ) -> int:
        """Calculate a lifecycle health score (0-100)."""
        base = self._estimate_score(history)

        # Stage bonus
        if stage == "HOT":
            base += 10
        elif stage == "RISING":
            base += 5
        elif stage == "DECLINE":
            base -= 10

        return max(0, min(100, int(base)))
