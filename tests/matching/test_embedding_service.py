"""Tests for Phase 34: EmbeddingService — lightweight text-to-vector."""

from __future__ import annotations

import math

import pytest

from app.matching.embedding_service import EmbeddingService


# ── Helpers ──────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _l2_norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


# ── Basic Encoding ──────────────────────────────────────────


class TestBasicEncoding:
    """Basic vector encoding functionality."""

    def test_encode_returns_list_of_floats(self):
        service = EmbeddingService(dim=128)
        vec = service.encode_text("三只松鼠坚果礼盒装")
        assert isinstance(vec, list)
        assert len(vec) == 128
        assert all(isinstance(v, float) for v in vec)

    def test_encode_fixed_dimension(self):
        for dim in [64, 128, 256, 512]:
            service = EmbeddingService(dim=dim)
            vec = service.encode_text("坚果礼盒")
            assert len(vec) == dim

    def test_custom_dimension(self):
        service = EmbeddingService(dim=100)
        vec = service.encode_text("测试文本")
        assert len(vec) == 100

    def test_encode_consistency(self):
        """Same text always produces same vector."""
        service = EmbeddingService(dim=128)
        text = "三只松鼠坚果礼盒装2024新款"
        v1 = service.encode_text(text)
        v2 = service.encode_text(text)
        assert v1 == pytest.approx(v2)


# ── Empty / Edge Cases ──────────────────────────────────────


class TestEdgeCases:
    """Empty and edge case handling."""

    def test_empty_text_returns_zeros(self):
        service = EmbeddingService(dim=128)
        vec = service.encode_text("")
        assert vec == [0.0] * 128

    def test_whitespace_text_returns_zeros(self):
        service = EmbeddingService(dim=64)
        vec = service.encode_text("   \t\n  ")
        assert vec == [0.0] * 64

    def test_single_character(self):
        service = EmbeddingService(dim=128)
        vec = service.encode_text("果")
        assert len(vec) == 128
        # Should have at least one non-zero value
        assert any(v > 0 for v in vec)

    def test_very_long_text(self):
        service = EmbeddingService(dim=128)
        long_text = "三只松鼠坚果礼盒" * 50
        vec = service.encode_text(long_text)
        assert len(vec) == 128


# ── Similarity Properties ───────────────────────────────────


class TestSimilarity:
    """Similarity-related properties of encoded vectors."""

    def test_similar_texts_higher_similarity(self):
        service = EmbeddingService(dim=256)
        v1 = service.encode_text("三只松鼠坚果礼盒装")
        v2 = service.encode_text("三只松鼠坚果大礼包")
        v3 = service.encode_text("无线蓝牙耳机降噪运动款")

        sim_similar = _cosine(v1, v2)
        sim_diff = _cosine(v1, v3)
        assert sim_similar > sim_diff, f"{sim_similar} vs {sim_diff}"

    def test_identical_text_max_similarity(self):
        service = EmbeddingService(dim=128)
        text = "坚果零食大礼包混合装"
        v1 = service.encode_text(text)
        v2 = service.encode_text(text)
        assert _cosine(v1, v2) == pytest.approx(1.0, abs=0.001)


# ── L2 Normalization ────────────────────────────────────────


class TestNormalization:
    """L2 normalization of output vectors."""

    def test_non_zero_vector_is_normalized(self):
        service = EmbeddingService(dim=128)
        vec = service.encode_text("三只松鼠坚果礼盒")
        norm = _l2_norm(vec)
        assert norm == pytest.approx(1.0, abs=0.001)

    def test_all_vectors_normalized(self):
        service = EmbeddingService(dim=64)
        texts = [
            "三只松鼠坚果礼盒装",
            "海苔卷零食大礼包",
            "无线蓝牙耳机",
            "short",
            "一个很长很长的商品标题用于测试向量是否总是归一化",
        ]
        for text in texts:
            vec = service.encode_text(text)
            if any(v > 0 for v in vec):
                assert _l2_norm(vec) == pytest.approx(1.0, abs=0.001)


# ── encode_product ──────────────────────────────────────────


class TestEncodeProduct:
    """encode_product method."""

    def test_encode_product_uses_title(self):
        service = EmbeddingService(dim=128)

        class FakeProduct:
            title = "坚果礼盒装"
            shop_name = ""
            category = None

        vec = service.encode_product(FakeProduct())
        assert len(vec) == 128
        # Should match encode_text of just the title
        expected = service.encode_text("坚果礼盒装")
        assert vec == pytest.approx(expected)

    def test_encode_product_with_category(self):
        service = EmbeddingService(dim=128)

        class FakeProduct:
            title = "坚果礼盒"
            shop_name = "零食店"
            category = "食品"

        vec = service.encode_product(FakeProduct())
        assert len(vec) == 128
        # With extra fields, should have non-zero values
        assert any(v > 0 for v in vec)

    def test_encode_product_without_category(self):
        service = EmbeddingService(dim=128)

        class FakeProduct:
            title = "测试商品"
            shop_name = ""
            category = None

        vec = service.encode_product(FakeProduct())
        title_vec = service.encode_text("测试商品")
        assert vec == pytest.approx(title_vec)


# ── Dimension Validation ────────────────────────────────────


class TestValidation:
    """Input validation."""

    def test_zero_dim_raises(self):
        with pytest.raises(ValueError):
            EmbeddingService(dim=0)

    def test_negative_dim_raises(self):
        with pytest.raises(ValueError):
            EmbeddingService(dim=-1)

    def test_positive_dim_ok(self):
        service = EmbeddingService(dim=1)
        vec = service.encode_text("测试")
        assert len(vec) == 1
