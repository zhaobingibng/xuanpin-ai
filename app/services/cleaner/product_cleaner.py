"""Product data cleaning and classification."""

import re


class ProductCleaner:
    """Clean, classify, and deduplicate raw product data."""

    # ── Ad words to strip from product names ──────────────────
    AD_WORDS: list[str] = ["包邮", "秒杀", "清仓", "爆款", "新款"]

    # ── Category keyword mapping ──────────────────────────────
    CATEGORY_MAP: dict[str, list[str]] = {
        "数码": ["手机", "耳机", "充电宝", "键盘"],
        "家居": ["水杯", "凉席", "收纳", "纸巾"],
        "服饰": ["衣服", "鞋", "包"],
    }

    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str]] = set()

    # ── Name cleaning ─────────────────────────────────────────

    def clean_name(self, name: str) -> str:
        """Clean a product name.

        - Remove emojis
        - Remove special symbols (keep Chinese, alphanumeric, spaces, /, -, .)
        - Remove ad words (包邮, 秒杀, 清仓, 爆款, 新款)
        - Collapse whitespace
        """
        if not name:
            return ""

        # Remove emojis — narrow, precise blocks only
        cleaned = re.sub(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended-A
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\u2600-\u26FF"          # misc symbols
            "\u2700-\u27BF"          # dingbats
            "\u23cf\u23e9-\u23f3\u23f8-\u23fa"  # misc technical
            "\u2640-\u2642"          # gender symbols
            "\u2660-\u2693"          # misc symbols
            "\u26aa-\u26ab"          # medium circles
            "\u2b50\u2b55"           # stars
            "\ufe0f"                 # variation selector
            "\u200d"                 # ZWJ
            "]+",
            "",
            name,
        )

        # Remove special symbols — keep Chinese, alphanumeric, spaces, /, -, .
        cleaned = re.sub(r"[^\u4e00-\u9fff\w\s/\-.]", "", cleaned)

        # Remove ad words
        for word in self.AD_WORDS:
            cleaned = cleaned.replace(word, "")

        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    # ── Classification ────────────────────────────────────────

    def classify(self, name: str) -> str:
        """Classify a product by keyword matching.

        Returns one of: 数码, 家居, 服饰, Other.
        """
        if not name:
            return "Other"

        for category, keywords in self.CATEGORY_MAP.items():
            for keyword in keywords:
                if keyword in name:
                    return category

        return "Other"

    # ── Deduplication ─────────────────────────────────────────

    def deduplicate(self, name: str, shop: str, platform: str) -> bool:
        """Check if a product is a duplicate.

        Rule: name + shop + platform.

        Returns True if the product has been seen before (duplicate).
        Automatically records the product as seen.
        """
        key = (name, shop, platform)
        if key in self._seen:
            return True
        self._seen.add(key)
        return False

    def reset(self) -> None:
        """Clear the deduplication history."""
        self._seen.clear()
