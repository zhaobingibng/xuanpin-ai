"""FeatureExtractor — 从中文电商标题中提取结构化特征。

支持提取：核心关键词、重量、包装类型、目标人群。
"""

from __future__ import annotations

import re
from typing import Any

import jieba


# ── Noise keywords to filter ──────────────────────────────────

_NOISE_KEYWORDS = frozenset({
    "爆款", "新品", "厂家", "批发", "包邮", "代发", "促销",
    "热销", "新款", "同款", "直销", "供应", "货源",
    "一件代发", "热卖", "正品", "特价", "清仓", "秒杀",
    "限时", "抢购", "优惠", "打折", "满减", "包邮",
})

# ── Stopwords for keyword extraction (extended) ──────────────

_KEYWORD_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "它", "们", "那", "些", "什么", "怎么", "如何", "为什么",
    "可以", "对", "中", "为", "与", "及", "等", "或", "个",
    "g", "kg", "ml", "l", "g克", "千克", "毫升", "升",
    "袋装", "桶装", "盒装", "礼盒", "散装", "罐装", "瓶装",
    "儿童", "学生", "办公室", "女生", "老人", "男士", "女士",
    "2024", "2025", "2026", "年", "月", "日",
})

# ── Weight patterns ───────────────────────────────────────────

_WEIGHT_PATTERNS = [
    # "50g", "100克", "500ml", "1kg", "2.5kg"
    (re.compile(r"(\d+\.?\d*)\s*(g|克)"), "g"),
    (re.compile(r"(\d+\.?\d*)\s*(kg|千克|公斤)"), "kg"),
    (re.compile(r"(\d+\.?\d*)\s*(ml|毫升)"), "ml"),
    (re.compile(r"(\d+\.?\d*)\s*(l|升)"), "l"),
    (re.compile(r"(\d+\.?\d*)\s*(斤)"), "斤"),
]

# ── Package keywords ──────────────────────────────────────────

_PACKAGE_KEYWORDS = ["礼盒", "袋装", "桶装", "盒装", "散装", "罐装", "瓶装"]

# ── Target audience keywords ──────────────────────────────────

_TARGET_KEYWORDS = ["儿童", "学生", "办公室", "女生", "老人", "男士", "女士"]


class FeatureExtractor:
    """从中文电商标题提取结构化特征。

    Usage:
        extractor = FeatureExtractor()
        features = extractor.extract("海苔卷零食50g桶装儿童")
        # {
        #     "keywords": ["海苔", "卷", "零食"],
        #     "category": "食品",
        #     "weight_value": 50,
        #     "weight_unit": "g",
        #     "package": "桶装",
        #     "target": "儿童",
        # }
    """

    def extract(self, title: str) -> dict[str, Any]:
        """Extract features from a Chinese e-commerce title.

        Args:
            title: Product title.

        Returns:
            Dict with keys: keywords, category, weight_value,
            weight_unit, package, target.
        """
        result: dict[str, Any] = {
            "keywords": [],
            "category": "",
            "weight_value": 0.0,
            "weight_unit": "",
            "package": "",
            "target": "",
        }

        if not title or not title.strip():
            return result

        title = title.strip()

        # 1. Extract keywords (noise-filtered)
        result["keywords"] = self._extract_keywords(title)

        # 2. Extract category from keywords
        result["category"] = self._infer_category(result["keywords"])

        # 3. Extract weight
        weight_info = self._extract_weight(title)
        result["weight_value"] = weight_info[0]
        result["weight_unit"] = weight_info[1]

        # 4. Extract package type
        result["package"] = self._extract_package(title)

        # 5. Extract target audience
        result["target"] = self._extract_target(title)

        return result

    # ── Keyword extraction ────────────────────────────────────

    def _extract_keywords(self, title: str) -> list[str]:
        """Extract meaningful keywords from title.

        Uses jieba + noise filtering.
        """
        # Clean
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", title)
        text = text.lower()

        # Tokenize
        words = jieba.lcut(text)

        # Filter
        keywords = []
        for w in words:
            w = w.strip()
            if len(w) < 2:
                continue
            if w in _KEYWORD_STOPWORDS:
                continue
            if w in _NOISE_KEYWORDS:
                continue
            keywords.append(w)

        return keywords

    # ── Category inference ────────────────────────────────────

    @staticmethod
    def _infer_category(keywords: list[str]) -> str:
        """Infer product category from keywords."""
        # Simple keyword-based category mapping
        category_map: dict[str, str] = {
            "零食": "食品",
            "坚果": "食品",
            "饼干": "食品",
            "糖果": "食品",
            "海苔": "食品",
            "巧克力": "食品",
            "茶叶": "食品",
            "饮料": "食品",
            "耳机": "数码",
            "手机": "数码",
            "蓝牙": "数码",
            "充电": "数码",
            "数据线": "数码",
            "键盘": "数码",
            "鼠标": "数码",
            "衣服": "服饰",
            "鞋子": "服饰",
            "包": "服饰",
            "帽子": "服饰",
            "围巾": "服饰",
            "清洁": "日用品",
            "纸巾": "日用品",
            "洗衣": "日用品",
            "收纳": "日用品",
            "文具": "办公",
            "笔记本": "办公",
            "笔": "办公",
            "玩具": "玩具",
            "积木": "玩具",
            "娃娃": "玩具",
        }

        scores: dict[str, int] = {}
        for kw in keywords:
            cat = category_map.get(kw)
            if cat:
                scores[cat] = scores.get(cat, 0) + 1

        if scores:
            return max(scores, key=lambda k: scores[k])
        return ""

    # ── Weight extraction ─────────────────────────────────────

    def _extract_weight(self, title: str) -> tuple[float, str]:
        """Extract weight info from title.

        Returns:
            (weight_value, weight_unit) — e.g. (50.0, "g").
        """
        for pattern, unit in _WEIGHT_PATTERNS:
            match = pattern.search(title)
            if match:
                value = float(match.group(1))
                return (value, unit)
        return (0.0, "")

    # ── Package extraction ────────────────────────────────────

    def _extract_package(self, title: str) -> str:
        """Extract package type from title."""
        for pkg in _PACKAGE_KEYWORDS:
            if pkg in title:
                return pkg
        return ""

    # ── Target audience extraction ────────────────────────────

    def _extract_target(self, title: str) -> str:
        """Extract target audience from title."""
        for target in _TARGET_KEYWORDS:
            if target in title:
                return target
        return ""
