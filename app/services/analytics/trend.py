"""Trend calculation utilities for product history data."""

from __future__ import annotations


def growth_rate(earliest: float, latest: float) -> float:
    """Calculate percentage growth rate between two values.

    Args:
        earliest: the earlier (older) value.
        latest: the later (newer) value.

    Returns:
        Percentage growth (positive = increase, negative = decrease).
        Returns 0.0 if earliest is 0.
    """
    if earliest == 0:
        return 0.0
    return round((latest - earliest) / earliest * 100, 2)


def growth_to_score(rate: float) -> float:
    """Convert a percentage growth rate to a 0–100 score.

    Mapping:
        rate <= -100% → 0
        rate == 0%    → 50
        rate >= +100% → 100
        linear in between.

    Args:
        rate: percentage growth rate.

    Returns:
        Score between 0.0 and 100.0, rounded to 2 decimals.
    """
    score = 50 + rate / 2
    return round(max(0.0, min(100.0, score)), 2)
