"""Data normalization utilities for raw product data."""

import re


def price_normalize(value: str | float | int) -> float | None:
    """Normalize price strings to float.

    Supported formats::

        "¥39.9"   → 39.9
        "￥39.9"   → 39.9
        "39元"    → 39.0
        "39.90"   → 39.9
        "39"      → 39.0
        39.9      → 39.9

    Returns None for invalid input.
    """
    if isinstance(value, int | float):
        return float(value)

    if not isinstance(value, str):
        return None

    try:
        # Strip currency symbols and unit suffixes
        cleaned = value.strip()
        cleaned = cleaned.replace("¥", "").replace("￥", "").replace("元", "")
        cleaned = cleaned.strip()

        if not cleaned:
            return None

        return float(cleaned)

    except (ValueError, TypeError):
        return None


def sales_normalize(value: str | int) -> int | None:
    """Normalize sales count strings to int.

    Supported formats::

        "1.2万"   → 12000
        "3.5w"    → 35000
        "1.5亿"   → 150000000
        "12000"   → 12000
        "12000+"  → 12000
        12000     → 12000

    Returns None for invalid input.
    """
    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if not isinstance(value, str):
        return None

    try:
        text = value.strip().rstrip("+")

        if not text:
            return None

        # 亿
        match = re.search(r"([\d.]+)\s*亿", text)
        if match:
            return int(float(match.group(1)) * 100_000_000)

        # 万 or w
        match = re.search(r"([\d.]+)\s*[万wW]", text)
        if match:
            return int(float(match.group(1)) * 10_000)

        # Plain number
        match = re.search(r"[\d.]+", text)
        if match:
            return int(float(match.group()))

        return None

    except (ValueError, TypeError):
        return None
