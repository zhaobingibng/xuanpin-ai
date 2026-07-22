"""Matching package — product matching engine."""

from app.matching.text_matcher import TextMatcher
from app.matching.feature_extractor import FeatureExtractor
from app.matching.fusion_matcher import FusionMatcher
from app.matching.product_matcher import ProductMatcher

__all__ = ["TextMatcher", "FeatureExtractor", "FusionMatcher", "ProductMatcher"]
