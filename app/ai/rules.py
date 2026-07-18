"""Scoring rules, weights, and dimension functions for product evaluation."""

from __future__ import annotations

# ── Weights (must sum to 1.0) ─────────────────────────────────
WEIGHTS: dict[str, float] = {
    "sales": 0.40,
    "viewers": 0.35,
    "price": 0.25,
}

# ── Sales scoring (higher = better) ───────────────────────────
# Thresholds: sales_24h → score
SALES_THRESHOLDS: list[tuple[int, float]] = [
    (10000, 100.0),
    (5000, 80.0),
    (1000, 60.0),
    (500, 40.0),
    (100, 20.0),
    (0, 0.0),
]

# ── Viewers scoring (higher = better) ─────────────────────────
VIEWER_THRESHOLDS: list[tuple[int, float]] = [
    (50000, 100.0),
    (10000, 80.0),
    (5000, 60.0),
    (1000, 40.0),
    (100, 20.0),
    (0, 0.0),
]

# ── Price scoring (sweet-spot curve) ──────────────────────────
# Optimal range: ¥50-300 (most likely to be a hit product)
PRICE_OPTIMAL_LOW: float = 50.0
PRICE_OPTIMAL_HIGH: float = 300.0
PRICE_MAX: float = 5000.0


def score_sales(sales: int) -> float:
    """Score sales_24h on a 0-100 scale.

    Uses step thresholds — higher sales → higher score.
    """
    for threshold, score in SALES_THRESHOLDS:
        if sales >= threshold:
            return score
    return 0.0


def score_viewers(viewers: int) -> float:
    """Score viewers on a 0-100 scale.

    Uses step thresholds — more viewers → higher score.
    """
    for threshold, score in VIEWER_THRESHOLDS:
        if viewers >= threshold:
            return score
    return 0.0


def score_price(price: float) -> float:
    """Score price on a 0-100 scale using a sweet-spot curve.

    ¥50-300 is optimal (score 80-100).
    Below ¥50 or above ¥300 gradually decreases.
    """
    if price <= 0:
        return 0.0

    if PRICE_OPTIMAL_LOW <= price <= PRICE_OPTIMAL_HIGH:
        # Optimal range: 80-100
        mid = (PRICE_OPTIMAL_LOW + PRICE_OPTIMAL_HIGH) / 2
        dist = abs(price - mid) / (mid - PRICE_OPTIMAL_LOW)
        return 100.0 - dist * 20.0  # 100 at center, 80 at edges

    if price < PRICE_OPTIMAL_LOW:
        # Below optimal: linear from 0 to 80
        return (price / PRICE_OPTIMAL_LOW) * 80.0

    # Above optimal: linear decay from 80 to 0
    if price >= PRICE_MAX:
        return 0.0
    return 80.0 * (1.0 - (price - PRICE_OPTIMAL_HIGH) / (PRICE_MAX - PRICE_OPTIMAL_HIGH))


def calculate_score(sales: int, viewers: int, price: float) -> float:
    """Calculate weighted composite score (0-100)."""
    s = score_sales(sales) * WEIGHTS["sales"]
    v = score_viewers(viewers) * WEIGHTS["viewers"]
    p = score_price(price) * WEIGHTS["price"]
    return round(s + v + p, 2)
