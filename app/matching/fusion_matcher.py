"""FusionMatcher — 文本+特征+图片融合评分。

计算综合评分（向后兼容）：

    无 image_score（旧接口）:
        final_score = text_score * 0.6 + feature_score * 0.4

    有 image_score（新接口）:
        final_score = text_score * 0.4 + feature_score * 0.3 + image_score * 0.3

其中 feature_score 基于：
- 关键词重叠 (Jaccard)
- 重量匹配
- 包装匹配
- 目标人群匹配
"""

from __future__ import annotations

from typing import Any

from app.matching.feature_extractor import FeatureExtractor


class FusionMatcher:
    """融合评分器：结合文本相似度、特征相似度和图片相似度。

    权重分配（新版，传入 image_score 时）:
        text_score    * 0.4  (来自 TextMatcher)
        feature_score * 0.3  (来自特征匹配)
        image_score   * 0.3  (来自 ImageMatcher)

    旧版权重（image_score 未传时保持兼容）:
        text_score    * 0.6
        feature_score * 0.4

    Usage:
        fusion = FusionMatcher()

        # 新接口（含图片分数）
        result = fusion.calculate(
            text_score=0.8,
            query_features=query_feat,
            candidate_features=cand_feat,
            image_score=0.9,
        )

        # 旧接口（仅文本+特征，向后兼容）
        result = fusion.calculate(
            text_score=0.8,
            query_features=query_feat,
            candidate_features=cand_feat,
        )
    """

    def __init__(self, extractor: FeatureExtractor | None = None) -> None:
        """Initialize FusionMatcher.

        Args:
            extractor: Optional FeatureExtractor instance. Creates default if None.
        """
        self._extractor = extractor or FeatureExtractor()

    # ── Public API ────────────────────────────────────────────

    def calculate(
        self,
        text_score: float,
        query_features: dict[str, Any],
        candidate_features: dict[str, Any],
        image_score: float | None = None,
    ) -> dict[str, float]:
        """Calculate final fused score.

        Args:
            text_score: Similarity score from TextMatcher [0, 1].
            query_features: Feature dict for query title.
            candidate_features: Feature dict for candidate title.
            image_score: Optional image similarity from ImageMatcher [0, 1].
                When None (default), uses old formula (text*0.6 + feature*0.4).
                When provided, uses new formula (text*0.4 + feature*0.3 + image*0.3).

        Returns:
            Dict with keys: text_score, feature_score, final_score,
            and image_score (only when provided).
        """
        feature_score = self._calculate_feature_score(
            query_features, candidate_features
        )

        if image_score is not None:
            # New formula: text*0.4 + feature*0.3 + image*0.3
            final_score = text_score * 0.4 + feature_score * 0.3 + image_score * 0.3
        else:
            # Old formula (backward compatible): text*0.6 + feature*0.4
            final_score = text_score * 0.6 + feature_score * 0.4

        result: dict[str, float] = {
            "text_score": round(text_score, 4),
            "feature_score": round(feature_score, 4),
            "final_score": round(final_score, 4),
        }

        if image_score is not None:
            result["image_score"] = round(image_score, 4)

        return result

    def extract_features(self, title: str) -> dict[str, Any]:
        """Extract features from a title.

        Args:
            title: Product title.

        Returns:
            Feature dict.
        """
        return self._extractor.extract(title)

    # ── Feature score calculation ─────────────────────────────

    def _calculate_feature_score(
        self,
        query: dict[str, Any],
        candidate: dict[str, Any],
    ) -> float:
        """Calculate feature-based similarity score.

        Components and their weights:
        - Keyword overlap: 0.40
        - Category match: 0.20
        - Weight match:   0.15
        - Package match:  0.15
        - Target match:   0.10

        Returns:
            Score in [0, 1].
        """
        # If neither side has any features, return 0 (to avoid spurious scores)
        has_query = bool(
            query.get("keywords") or query.get("category")
            or query.get("weight_value") or query.get("package") or query.get("target")
        )
        has_candidate = bool(
            candidate.get("keywords") or candidate.get("category")
            or candidate.get("weight_value") or candidate.get("package") or candidate.get("target")
        )
        if not has_query or not has_candidate:
            return 0.0

        weights = {
            "keyword": 0.40,
            "category": 0.20,
            "weight": 0.15,
            "package": 0.15,
            "target": 0.10,
        }

        # 1. Keyword overlap (Jaccard)
        keyword_score = self._jaccard(
            set(query.get("keywords", [])),
            set(candidate.get("keywords", [])),
        )

        # 2. Category match
        cat_score = 1.0 if (
            query.get("category") and query["category"] == candidate.get("category")
        ) else 0.0

        # 3. Weight match
        weight_score = self._match_weight(query, candidate)

        # 4. Package match
        pkg_score = self._match_field(query, candidate, "package")

        # 5. Target match
        target_score = self._match_field(query, candidate, "target")

        total = (
            weights["keyword"] * keyword_score
            + weights["category"] * cat_score
            + weights["weight"] * weight_score
            + weights["package"] * pkg_score
            + weights["target"] * target_score
        )

        return min(total, 1.0)

    # ── Sub-score helpers ─────────────────────────────────────

    @staticmethod
    def _jaccard(set1: set, set2: set) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        if union == 0:
            return 0.0
        return intersection / union

    @staticmethod
    def _match_weight(
        query: dict[str, Any],
        candidate: dict[str, Any],
    ) -> float:
        """Calculate weight match score.

        Full match (same value + unit): 1.0
        Same unit, close value (within 20%): 0.6
        Both have weight but different: 0.3
        One has weight, other doesn't: 0.0
        Neither has weight: 0.5 (neutral)
        """
        q_val = query.get("weight_value", 0)
        q_unit = query.get("weight_unit", "")
        c_val = candidate.get("weight_value", 0)
        c_unit = candidate.get("weight_unit", "")

        has_q = bool(q_val and q_unit)
        has_c = bool(c_val and c_unit)

        if not has_q and not has_c:
            return 0.5  # Neutral — both no weight info

        if not has_q or not has_c:
            return 0.0  # Only one has weight info

        # Same unit?
        if q_unit != c_unit:
            return 0.2  # Different units

        # Same value?
        if q_val == c_val:
            return 1.0

        # Close values (within 20%)?
        max_val = max(q_val, c_val)
        min_val = min(q_val, c_val)
        if max_val > 0 and (max_val - min_val) / max_val <= 0.2:
            return 0.6

        return 0.3  # Same unit but very different values

    @staticmethod
    def _match_field(
        query: dict[str, Any],
        candidate: dict[str, Any],
        field: str,
    ) -> float:
        """Calculate match score for a single string field.

        Both have same value: 1.0
        Both have different values: 0.3
        One has value: 0.0
        Neither has value: 0.5 (neutral)
        """
        q_val = query.get(field, "")
        c_val = candidate.get(field, "")

        has_q = bool(q_val)
        has_c = bool(c_val)

        if not has_q and not has_c:
            return 0.5  # Neutral

        if not has_q or not has_c:
            return 0.0

        return 1.0 if q_val == c_val else 0.3
