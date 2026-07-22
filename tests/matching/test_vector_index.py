"""Tests for Phase 34: VectorIndex — cosine similarity search."""

from __future__ import annotations

import math

import pytest

from app.matching.vector_index import VectorIndex


# ── Helpers ──────────────────────────────────────────────────

def _make_vec(*values: float, dim: int = 8) -> list[float]:
    """Create a dense vector of given dimension, filling with values."""
    result = [0.0] * dim
    for i, v in enumerate(values):
        if i < dim:
            result[i] = float(v)
    return result


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


# ── Add & Search ────────────────────────────────────────────


class TestAddAndSearch:
    """Basic add and search operations."""

    def test_add_and_search_single(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        results = idx.search(_make_vec(1.0, 0.0), top_k=10)
        assert len(results) == 1
        assert results[0][0] == 1
        assert results[0][1] == pytest.approx(1.0)

    def test_search_returns_sorted(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        idx.add(2, _make_vec(0.8, 0.2))
        idx.add(3, _make_vec(0.0, 1.0))

        results = idx.search(_make_vec(1.0, 0.0), top_k=10)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0][0] == 1  # most similar

    def test_search_with_identical_vector(self):
        idx = VectorIndex()
        vec = _make_vec(0.5, 0.5, 0.5, 0.5)
        idx.add(42, vec)
        results = idx.search(vec, top_k=5)
        assert results[0][0] == 42
        assert results[0][1] == pytest.approx(1.0, abs=0.001)


# ── Top-K ───────────────────────────────────────────────────


class TestTopK:
    """Top-k result limiting."""

    def test_top_k_limits_results(self):
        idx = VectorIndex()
        for i in range(10):
            idx.add(i, _make_vec(float(i) / 10, 0.0))
        results = idx.search(_make_vec(1.0, 0.0), top_k=3)
        assert len(results) == 3

    def test_top_k_greater_than_items(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        idx.add(2, _make_vec(0.0, 1.0))
        results = idx.search(_make_vec(1.0, 0.0), top_k=100)
        assert len(results) == 2  # only 2 items

    def test_top_k_zero_returns_empty(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        results = idx.search(_make_vec(1.0), top_k=0)
        assert results == []

    def test_top_k_negative_returns_empty(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        results = idx.search(_make_vec(1.0), top_k=-1)
        assert results == []


# ── Empty Index ─────────────────────────────────────────────


class TestEmptyIndex:
    """Empty index behavior."""

    def test_search_empty_index(self):
        idx = VectorIndex()
        results = idx.search(_make_vec(1.0, 0.0))
        assert results == []

    def test_search_none_query(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        results = idx.search(None)
        assert results == []


# ── Delete ──────────────────────────────────────────────────


class TestDelete:
    """Delete operations."""

    def test_delete_existing(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        assert 1 in idx
        assert idx.delete(1) is True
        assert 1 not in idx

    def test_delete_nonexistent(self):
        idx = VectorIndex()
        assert idx.delete(999) is False

    def test_search_after_delete(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        idx.add(2, _make_vec(0.0, 1.0))
        idx.delete(1)

        results = idx.search(_make_vec(1.0, 0.0))
        assert len(results) == 1
        assert results[0][0] == 2

    def test_delete_then_re_add(self):
        idx = VectorIndex()
        vec1 = _make_vec(1.0, 0.0)
        idx.add(1, vec1)
        idx.delete(1)
        idx.add(1, _make_vec(0.0, 1.0))
        results = idx.search(_make_vec(0.0, 1.0))
        assert results[0][0] == 1
        assert results[0][1] == pytest.approx(1.0)


# ── Update ──────────────────────────────────────────────────


class TestUpdate:
    """Update (duplicate add) operations."""

    def test_add_duplicate_overwrites(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        idx.add(1, _make_vec(0.0, 1.0))
        # Should now match the second vector
        results = idx.search(_make_vec(0.0, 1.0))
        assert results[0][0] == 1
        assert results[0][1] == pytest.approx(1.0)


# ── Similarity Score ────────────────────────────────────────


class TestSimilarityScore:
    """Cosine similarity score accuracy."""

    def test_orthogonal_vectors_zero(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0))
        results = idx.search(_make_vec(0.0, 1.0))
        assert results[0][1] == pytest.approx(0.0, abs=0.001)

    def test_scores_in_range(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0, 0.0))
        idx.add(2, _make_vec(0.5, 0.5, 0.5))
        idx.add(3, _make_vec(0.0, 1.0, 0.0))

        results = idx.search(_make_vec(1.0, 0.0, 0.0))
        for _, score in results:
            assert 0.0 <= score <= 1.0


# ── Dimension Mismatch ──────────────────────────────────────


class TestDimensionMismatch:
    """Dimension mismatch handling."""

    def test_dimension_mismatch_raises(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0, 0.0, dim=8))
        with pytest.raises(ValueError):
            idx.search(_make_vec(1.0, dim=4))

    def test_add_none_raises(self):
        idx = VectorIndex()
        with pytest.raises(ValueError):
            idx.add(1, None)


# ── Len & Contains ──────────────────────────────────────────


class TestLenContains:
    """Length and containment checks."""

    def test_len_empty(self):
        assert len(VectorIndex()) == 0

    def test_len_after_add(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        idx.add(2, _make_vec(2.0))
        assert len(idx) == 2

    def test_len_after_delete(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        idx.add(2, _make_vec(2.0))
        idx.delete(1)
        assert len(idx) == 1

    def test_contains(self):
        idx = VectorIndex()
        idx.add(42, _make_vec(1.0))
        assert 42 in idx
        assert 99 not in idx

    def test_item_ids(self):
        idx = VectorIndex()
        idx.add(1, _make_vec(1.0))
        idx.add(2, _make_vec(2.0))
        assert set(idx.item_ids) == {1, 2}


# ── Large Scale ─────────────────────────────────────────────


class TestLargeScale:
    """Large number of items."""

    def test_many_items(self):
        idx = VectorIndex()
        n = 200
        for i in range(n):
            idx.add(i, _make_vec(float(i % 10) / 10, float((i + 1) % 10) / 10))
        assert len(idx) == n
        results = idx.search(_make_vec(0.9, 0.1), top_k=10)
        assert len(results) == 10
        # Results sorted descending
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)
