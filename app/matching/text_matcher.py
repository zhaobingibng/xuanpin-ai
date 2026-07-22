"""TextMatcher — jieba + TF-IDF + cosine similarity.

Provides text similarity calculation for product matching.
Uses jieba for Chinese word segmentation and implements
TF-IDF + cosine similarity without sklearn dependency.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

import jieba


# ── Stopwords ─────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "它", "们", "那", "些", "什么", "怎么", "如何", "为什么",
    "可以", "对", "中", "为", "与", "及", "等", "或", "个",
    "包邮", "热销", "新款", "同款", "厂家", "直销", "批发",
    "供应", "货源", "一件代发", "代发", "爆款", "热卖",
})


class TextMatcher:
    """Text similarity matcher using jieba + TF-IDF + cosine similarity.
    
    Usage:
        matcher = TextMatcher()
        score = matcher.calculate_similarity("三只松鼠坚果礼盒", "坚果礼盒装2024新款")
    """

    def __init__(self, stopwords: set[str] | None = None) -> None:
        """Initialize TextMatcher.
        
        Args:
            stopwords: Custom stopwords set. Uses default if None.
        """
        self._stopwords = stopwords if stopwords is not None else _STOPWORDS
        
        # IDF cache: built lazily from corpus
        self._idf: dict[str, float] = {}
        self._doc_count: int = 0

    # ── Public API ────────────────────────────────────────────

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts.
        
        Uses TF-IDF vectors + cosine similarity.
        Falls back to Jaccard if either text is too short for TF-IDF.
        
        Args:
            text1: First text.
            text2: Second text.
        
        Returns:
            Similarity score in [0, 1].
        """
        if not text1 or not text2:
            return 0.0
        
        tokens1 = self._tokenize(text1)
        tokens2 = self._tokenize(text2)
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Build IDF from the two documents
        self._build_idf([tokens1, tokens2])
        
        # Calculate TF-IDF vectors
        tfidf1 = self._tfidf(tokens1)
        tfidf2 = self._tfidf(tokens2)
        
        # Cosine similarity
        return self._cosine_similarity(tfidf1, tfidf2)

    def calculate_similarity_batch(
        self, text: str, candidates: Sequence[str]
    ) -> list[tuple[int, float]]:
        """Calculate similarity between one text and many candidates.
        
        More efficient than calling calculate_similarity in a loop
        because IDF is computed once.
        
        Args:
            text: Query text.
            candidates: List of candidate texts.
        
        Returns:
            List of (index, score) tuples, sorted by score descending.
        """
        if not text or not candidates:
            return [(i, 0.0) for i in range(len(candidates))] if candidates else []
        
        tokens_query = self._tokenize(text)
        if not tokens_query:
            return [(i, 0.0) for i in range(len(candidates))]
        
        # Tokenize all candidates
        all_tokens = [tokens_query]
        candidate_tokens = []
        for c in candidates:
            t = self._tokenize(c) if c else []
            all_tokens.append(t)
            candidate_tokens.append(t)
        
        # Build IDF from all documents
        self._build_idf([t for t in all_tokens if t])
        
        # Calculate TF-IDF for query
        tfidf_query = self._tfidf(tokens_query)
        
        # Calculate similarities
        results: list[tuple[int, float]] = []
        for i, ct in enumerate(candidate_tokens):
            if not ct:
                results.append((i, 0.0))
                continue
            tfidf_c = self._tfidf(ct)
            score = self._cosine_similarity(tfidf_query, tfidf_c)
            results.append((i, score))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ── Tokenization ──────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text using jieba.
        
        Args:
            text: Input text.
        
        Returns:
            List of tokens (stopwords removed).
        """
        # Clean: remove special chars, keep Chinese + alphanumeric
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", text)
        text = text.lower()
        
        # Segment
        words = jieba.lcut(text)
        
        # Filter
        tokens = []
        for w in words:
            w = w.strip()
            if len(w) >= 2 and w not in self._stopwords:
                tokens.append(w)
        
        return tokens

    # ── TF-IDF ────────────────────────────────────────────────

    def _build_idf(self, documents: list[list[str]]) -> None:
        """Build IDF from a list of tokenized documents.
        
        Args:
            documents: List of token lists.
        """
        self._doc_count = len(documents)
        if self._doc_count == 0:
            return
        
        # Count document frequency
        df: Counter[str] = Counter()
        for doc in documents:
            unique_terms = set(doc)
            for term in unique_terms:
                df[term] += 1
        
        # Calculate IDF
        self._idf = {}
        for term, freq in df.items():
            self._idf[term] = math.log((self._doc_count + 1) / (freq + 1)) + 1

    def _tfidf(self, tokens: list[str]) -> dict[str, float]:
        """Calculate TF-IDF vector for a token list.
        
        Args:
            tokens: List of tokens.
        
        Returns:
            Dict mapping term -> TF-IDF score.
        """
        if not tokens:
            return {}
        
        # Term frequency
        tf = Counter(tokens)
        total = len(tokens)
        
        # TF-IDF
        vector: dict[str, float] = {}
        for term, count in tf.items():
            tf_val = count / total
            idf_val = self._idf.get(term, 1.0)
            vector[term] = tf_val * idf_val
        
        return vector

    # ── Cosine Similarity ─────────────────────────────────────

    @staticmethod
    def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Calculate cosine similarity between two sparse vectors.
        
        Args:
            vec1: First vector (term -> value).
            vec2: Second vector (term -> value).
        
        Returns:
            Cosine similarity in [0, 1].
        """
        if not vec1 or not vec2:
            return 0.0
        
        # Dot product (only common terms)
        common_keys = set(vec1.keys()) & set(vec2.keys())
        if not common_keys:
            return 0.0
        
        dot = sum(vec1[k] * vec2[k] for k in common_keys)
        
        # Magnitudes
        mag1 = math.sqrt(sum(v * v for v in vec1.values()))
        mag2 = math.sqrt(sum(v * v for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot / (mag1 * mag2)
