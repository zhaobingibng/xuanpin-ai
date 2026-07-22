"""Tests for Phase 27: TextMatcher."""

import pytest

from app.matching.text_matcher import TextMatcher


class TestTokenization:
    """Test jieba tokenization."""

    def test_chinese_tokenization(self):
        """Should tokenize Chinese text correctly."""
        matcher = TextMatcher()
        tokens = matcher._tokenize("三只松鼠坚果礼盒装")
        assert len(tokens) > 0
        # Should contain meaningful tokens
        assert any("坚果" in t for t in tokens)

    def test_mixed_tokenization(self):
        """Should handle mixed Chinese and English."""
        matcher = TextMatcher()
        tokens = matcher._tokenize("2024新款坚果礼盒nut gift box")
        assert len(tokens) > 0

    def test_stopwords_removed(self):
        """Should remove stopwords."""
        matcher = TextMatcher()
        tokens = matcher._tokenize("我的坚果礼盒")
        # "我" and "的" should be removed
        assert "我" not in tokens
        assert "的" not in tokens

    def test_short_tokens_filtered(self):
        """Should filter tokens shorter than 2 chars."""
        matcher = TextMatcher()
        tokens = matcher._tokenize("好的大坚果")
        # Single char tokens should be filtered
        assert all(len(t) >= 2 for t in tokens)


class TestCalculateSimilarity:
    """Test calculate_similarity method."""

    def test_identical_texts(self):
        """Identical texts should have high similarity."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity(
            "三只松鼠坚果礼盒装",
            "三只松鼠坚果礼盒装",
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_similar_texts(self):
        """Similar texts should have moderate-high similarity."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity(
            "三只松鼠坚果礼盒装2024新款",
            "坚果礼盒装零食大礼包",
        )
        assert 0.2 < score < 1.0

    def test_different_texts(self):
        """Completely different texts should have low similarity."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity(
            "三只松鼠坚果礼盒",
            "无线蓝牙耳机降噪",
        )
        assert score < 0.3

    def test_empty_text1(self):
        """Empty first text should return 0."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity("", "坚果礼盒")
        assert score == 0.0

    def test_empty_text2(self):
        """Empty second text should return 0."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity("坚果礼盒", "")
        assert score == 0.0

    def test_both_empty(self):
        """Both empty should return 0."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity("", "")
        assert score == 0.0

    def test_single_char_texts(self):
        """Single char texts should return 0 (filtered)."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity("的", "了")
        assert score == 0.0

    def test_synonym_products(self):
        """Synonym products should have some similarity."""
        matcher = TextMatcher()
        score = matcher.calculate_similarity(
            "海苔卷零食大礼包",
            "海苔脆卷即食小吃",
        )
        # Should share "海苔" token
        assert score > 0.0

    def test_score_range(self):
        """Score should be in [0, 1]."""
        matcher = TextMatcher()
        pairs = [
            ("坚果礼盒", "坚果礼盒"),
            ("坚果", "蓝牙耳机"),
            ("", "test"),
            ("abc", "def"),
        ]
        for t1, t2 in pairs:
            score = matcher.calculate_similarity(t1, t2)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for ({t1!r}, {t2!r})"


class TestBatchSimilarilarity:
    """Test calculate_similarity_batch method."""

    def test_batch_basic(self):
        """Batch should return sorted results."""
        matcher = TextMatcher()
        query = "坚果礼盒装"
        candidates = [
            "坚果礼盒装2024新款",
            "蓝牙耳机降噪",
            "零食大礼包坚果",
        ]
        results = matcher.calculate_similarity_batch(query, candidates)
        
        assert len(results) == 3
        # Should be sorted by score descending
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_batch_empty_query(self):
        """Empty query should return all zeros."""
        matcher = TextMatcher()
        results = matcher.calculate_similarity_batch("", ["坚果", "零食"])
        assert len(results) == 2
        assert all(s == 0.0 for _, s in results)

    def test_batch_empty_candidates(self):
        """Empty candidates should return empty list."""
        matcher = TextMatcher()
        results = matcher.calculate_similarity_batch("坚果", [])
        assert len(results) == 0

    def test_batch_top_match(self):
        """Best match should be first."""
        matcher = TextMatcher()
        query = "三只松鼠坚果礼盒"
        candidates = [
            "无线蓝牙耳机",       # irrelevant
            "三只松鼠坚果礼盒装",   # best match
            "零食大礼包",          # somewhat related
        ]
        results = matcher.calculate_similarity_batch(query, candidates)
        best_idx = results[0][0]
        assert best_idx == 1  # Second candidate is the best match


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1."""
        vec = {"坚果": 0.5, "礼盒": 0.3}
        score = TextMatcher._cosine_similarity(vec, vec)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_orthogonal_vectors(self):
        """Vectors with no common terms should have similarity 0."""
        vec1 = {"坚果": 0.5}
        vec2 = {"耳机": 0.5}
        score = TextMatcher._cosine_similarity(vec1, vec2)
        assert score == 0.0

    def test_empty_vector(self):
        """Empty vector should return 0."""
        score = TextMatcher._cosine_similarity({}, {"a": 1.0})
        assert score == 0.0

    def test_partial_overlap(self):
        """Vectors with partial overlap should have intermediate score."""
        vec1 = {"坚果": 0.5, "礼盒": 0.3}
        vec2 = {"坚果": 0.4, "零食": 0.6}
        score = TextMatcher._cosine_similarity(vec1, vec2)
        assert 0.0 < score < 1.0
