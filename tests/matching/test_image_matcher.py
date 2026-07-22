"""Tests for Phase 32: ImageMatcher — dHash image similarity."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image as PILImage

from app.matching.image_matcher import HAS_PIL, ImageMatcher


# ── Helpers ──────────────────────────────────────────────────

def _make_solid_image(width: int = 100, height: int = 100,
                      color: tuple[int, int, int] = (255, 0, 0),
                      mode: str = "RGB") -> PILImage.Image:
    """Create a simple solid-color PIL image."""
    return PILImage.new(mode, (width, height), color)


def _make_checkerboard_image(size: int = 100) -> PILImage.Image:
    """Create a simple checkerboard pattern image."""
    img = PILImage.new("L", (size, size), 128)
    for x in range(size):
        for y in range(size):
            if (x // 10 + y // 10) % 2 == 0:
                img.putpixel((x, y), 0)
            else:
                img.putpixel((x, y), 255)
    return img


def _image_to_bytes(img: PILImage.Image, fmt: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ── Test: import / init ──────────────────────────────────────

class TestImportAndInit:
    """Test module import and initialization."""

    def test_pillow_available(self):
        """HAS_PIL should be True (Pillow is a project dependency)."""
        assert HAS_PIL is True

    def test_init_default(self):
        """ImageMatcher should initialize without errors."""
        matcher = ImageMatcher()
        assert matcher.HASH_SIZE == 8

    def test_hash_size_constant(self):
        """HASH_SIZE should be 8 (64-bit hash)."""
        assert ImageMatcher.HASH_SIZE == 8


# ── Test: compute_hash ───────────────────────────────────────

class TestComputeHash:
    """Test compute_hash method."""

    def test_hash_is_16_char_hex(self):
        """dHash should return 16-char hex string."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(255, 0, 0))
        h = matcher.compute_hash(img)
        assert isinstance(h, str)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_image_same_hash(self):
        """Identical images produce identical hashes."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(0, 128, 255))
        h1 = matcher.compute_hash(img)
        h2 = matcher.compute_hash(img)
        assert h1 == h2

    def test_none_returns_none(self):
        """None input returns None."""
        matcher = ImageMatcher()
        assert matcher.compute_hash(None) is None

    def test_invalid_bytes_returns_none(self):
        """Invalid bytes return None."""
        matcher = ImageMatcher()
        assert matcher.compute_hash(b"not an image") is None

    def test_hash_from_bytes(self):
        """Bytes input produces valid hash."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(100, 200, 50))
        data = _image_to_bytes(img)
        h = matcher.compute_hash(data)
        assert h is not None
        assert len(h) == 16

    def test_hash_from_pil_same_as_bytes(self):
        """Hash from PIL Image == hash from bytes of same image."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(30, 60, 90))
        h_pil = matcher.compute_hash(img)
        h_bytes = matcher.compute_hash(_image_to_bytes(img))
        assert h_pil == h_bytes


# ── Test: calculate_similarity — basic ───────────────────────

class TestCalculateSimilarityBasic:
    """Test calculate_similarity basic cases."""

    def test_identical_images_perfect_score(self):
        """Two identical PIL images → 1.0."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(255, 100, 50))
        score = matcher.calculate_similarity(img, img)
        assert score == 1.0

    def test_different_patterns_not_identical(self):
        """Different visual patterns should score < 1.0.

        Note: dHash detects gradient differences, not color values.
        Two uniform-color images of any color produce identical (all-zero)
        hashes because they have no edges.  Real product images always have
        texture/edges, so this test uses patterns that simulate real images.
        """
        matcher = ImageMatcher()
        img_a = _make_checkerboard_image()
        img_b = _make_solid_image(color=(128, 128, 128))
        score = matcher.calculate_similarity(img_a, img_b)
        assert score < 1.0

    def test_similar_colors_high_score(self):
        """Very similar colors should produce high similarity."""
        matcher = ImageMatcher()
        img_a = _make_solid_image(color=(200, 100, 50))
        img_b = _make_solid_image(color=(205, 105, 55))
        score = matcher.calculate_similarity(img_a, img_b)
        assert score >= 0.7

    def test_score_in_range(self):
        """All similarity scores should be in [0, 1]."""
        matcher = ImageMatcher()
        test_pairs = [
            (_make_solid_image(color=(255, 0, 0)),
             _make_solid_image(color=(0, 0, 255))),
            (_make_solid_image(color=(128, 128, 128)),
             _make_checkerboard_image()),
            (_make_checkerboard_image(),
             _make_checkerboard_image()),
        ]
        for a, b in test_pairs:
            score = matcher.calculate_similarity(a, b)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range"

    def test_symmetry(self):
        """sim(a, b) should equal sim(b, a)."""
        matcher = ImageMatcher()
        img_a = _make_solid_image(color=(200, 100, 50))
        img_b = _make_solid_image(color=(205, 105, 55))
        s1 = matcher.calculate_similarity(img_a, img_b)
        s2 = matcher.calculate_similarity(img_b, img_a)
        assert s1 == pytest.approx(s2)


# ── Test: calculate_similarity — input types ─────────────────

class TestCalculateSimilarityInputs:
    """Test calculate_similarity with different input types."""

    def test_bytes_input(self):
        """Bytes input should work."""
        matcher = ImageMatcher()
        img_a = _make_solid_image(color=(255, 0, 0))
        img_b = _make_solid_image(color=(255, 0, 0))
        score = matcher.calculate_similarity(
            _image_to_bytes(img_a),
            _image_to_bytes(img_b),
        )
        assert score == 1.0

    def test_mixed_pil_and_bytes(self):
        """PIL Image vs bytes should work."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(128, 128, 128))
        score = matcher.calculate_similarity(img, _image_to_bytes(img))
        assert score == 1.0

    def test_none_input_returns_zero(self):
        """None input → 0.0."""
        matcher = ImageMatcher()
        img = _make_solid_image()
        assert matcher.calculate_similarity(None, img) == 0.0
        assert matcher.calculate_similarity(img, None) == 0.0
        assert matcher.calculate_similarity(None, None) == 0.0

    def test_invalid_bytes_returns_zero(self):
        """Invalid bytes → 0.0."""
        matcher = ImageMatcher()
        img = _make_solid_image()
        assert matcher.calculate_similarity(b"bad", img) == 0.0
        assert matcher.calculate_similarity(img, b"bad") == 0.0

    def test_file_not_found_returns_zero(self):
        """Non-existent file path → 0.0."""
        matcher = ImageMatcher()
        score = matcher.calculate_similarity(
            "/nonexistent/path/img.png",
            "/nonexistent/path/img2.png",
        )
        assert score == 0.0


# ── Test: calculate_similarity — real image bytes ────────────

class TestCalculateSimilarityRealBytes:
    """Test with real PNG/JPEG bytes (not just solid PIL images)."""

    def test_same_png_bytes_identical(self):
        """Same PNG bytes → 1.0."""
        matcher = ImageMatcher()
        img = _make_checkerboard_image()
        data = _image_to_bytes(img, "PNG")
        score = matcher.calculate_similarity(data, data)
        assert score == 1.0

    def test_png_vs_jpeg_same_content(self):
        """PNG vs JPEG of same content → high similarity."""
        matcher = ImageMatcher()
        img = _make_solid_image(color=(100, 150, 200))

        png_data = _image_to_bytes(img, "PNG")
        # For JPEG, need to convert to RGB
        jpeg_img = img.convert("RGB")
        buf = io.BytesIO()
        jpeg_img.save(buf, format="JPEG")
        jpeg_data = buf.getvalue()

        score = matcher.calculate_similarity(png_data, jpeg_data)
        # Same visual content → should be high (JPEG compression artifacts ok)
        assert score >= 0.9

    def test_different_checkerboard_patterns(self):
        """Different patterns → not identical."""
        matcher = ImageMatcher()
        cb1 = _make_checkerboard_image()
        cb2 = _make_solid_image(color=(128, 128, 128))

        score = matcher.calculate_similarity(cb1, cb2)
        assert score < 1.0


# ── Test: hamming distance ───────────────────────────────────

class TestHammingDistance:
    """Test _hamming_distance static method."""

    def test_same_hash_zero_distance(self):
        """Same hash → distance 0."""
        dist = ImageMatcher._hamming_distance("abcd1234abcd1234", "abcd1234abcd1234")
        assert dist == 0

    def test_all_different_max_distance(self):
        """All bits different → distance 64."""
        dist = ImageMatcher._hamming_distance("0000000000000000", "ffffffffffffffff")
        assert dist == 64

    def test_different_length_returns_max(self):
        """Different hash lengths → max distance 64."""
        dist = ImageMatcher._hamming_distance("abcd", "abcdef1234567890")
        assert dist == 64

    def test_partial_difference(self):
        """Known partial difference."""
        # 0x0001 vs 0x0000 → 1 bit different
        dist = ImageMatcher._hamming_distance(
            "0000000000000001",
            "0000000000000000",
        )
        assert dist == 1


# ── Test: similarity_from_hamming ────────────────────────────

class TestSimilarityFromHamming:
    """Test _similarity_from_hamming method."""

    def test_zero_distance_perfect(self):
        """0 distance → 1.0."""
        matcher = ImageMatcher()
        assert matcher._similarity_from_hamming(0) == 1.0

    def test_max_distance_zero(self):
        """64 distance → 0.0."""
        matcher = ImageMatcher()
        assert matcher._similarity_from_hamming(64) == 0.0

    def test_half_distance(self):
        """32 distance → 0.5."""
        matcher = ImageMatcher()
        assert matcher._similarity_from_hamming(32) == 0.5

    def test_monotonic(self):
        """Lower distance → higher similarity."""
        matcher = ImageMatcher()
        s1 = matcher._similarity_from_hamming(10)
        s2 = matcher._similarity_from_hamming(20)
        assert s1 > s2


# ── Test: different image sizes ──────────────────────────────

class TestDifferentSizes:
    """Test with images of different dimensions."""

    def test_same_content_different_size(self):
        """Same visual content at different sizes → high similarity."""
        matcher = ImageMatcher()
        img_small = _make_solid_image(width=50, height=50, color=(200, 100, 50))
        img_large = _make_solid_image(width=200, height=200, color=(200, 100, 50))

        score = matcher.calculate_similarity(img_small, img_large)
        # dHash resizes both to 9x8, so same solid color → perfect match
        assert score == 1.0

    def test_grayscale_vs_color(self):
        """Grayscale vs color of same content → high similarity."""
        matcher = ImageMatcher()
        img_rgb = _make_solid_image(color=(128, 128, 128))
        img_gray = PILImage.new("L", (100, 100), 128)

        score = matcher.calculate_similarity(img_rgb, img_gray)
        assert score == 1.0


# ── Test: FusionMatcher image_score integration ──────────────

class TestFusionMatcherWithImage:
    """Test FusionMatcher with image_score parameter."""

    def test_new_formula_with_image(self):
        """New formula: text*0.4 + feature*0.3 + image*0.3."""
        from app.matching.fusion_matcher import FusionMatcher
        from app.matching.feature_extractor import FeatureExtractor

        fusion = FusionMatcher()
        fe = {"keywords": ["坚果"], "category": "食品", "weight_value": 0.0,
              "weight_unit": "", "package": "", "target": ""}

        result = fusion.calculate(
            text_score=1.0,
            query_features=fe,
            candidate_features=fe,
            image_score=1.0,
        )

        # text*0.4 + feature*0.3 + image*0.3
        expected = 1.0 * 0.4 + result["feature_score"] * 0.3 + 1.0 * 0.3
        assert result["final_score"] == pytest.approx(expected, abs=0.01)
        assert result["image_score"] == 1.0

    def test_old_formula_without_image(self):
        """Without image_score → old formula text*0.6 + feature*0.4."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        fe = {"keywords": ["坚果"], "category": "食品", "weight_value": 0.0,
              "weight_unit": "", "package": "", "target": ""}

        result = fusion.calculate(
            text_score=1.0,
            query_features=fe,
            candidate_features=fe,
        )

        expected = 1.0 * 0.6 + result["feature_score"] * 0.4
        assert result["final_score"] == pytest.approx(expected, abs=0.01)
        assert "image_score" not in result

    def test_image_score_not_in_result_when_none(self):
        """image_score should NOT appear when not provided."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        fe = {"keywords": [], "category": "", "weight_value": 0.0,
              "weight_unit": "", "package": "", "target": ""}

        result = fusion.calculate(text_score=0.5, query_features=fe,
                                  candidate_features=fe)
        assert "image_score" not in result

    def test_image_score_in_result_when_provided(self):
        """image_score should appear in result when provided."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        fe = {"keywords": [], "category": "", "weight_value": 0.0,
              "weight_unit": "", "package": "", "target": ""}

        result = fusion.calculate(text_score=0.5, query_features=fe,
                                  candidate_features=fe, image_score=0.8)
        assert "image_score" in result
        assert result["image_score"] == 0.8

    def test_new_formula_lower_text_weight(self):
        """With image, text weight drops from 0.6 → 0.4."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        fe = {"keywords": ["坚果"], "category": "食品", "weight_value": 0.0,
              "weight_unit": "", "package": "", "target": ""}

        result_old = fusion.calculate(text_score=1.0, query_features=fe,
                                      candidate_features=fe)
        result_new = fusion.calculate(text_score=1.0, query_features=fe,
                                      candidate_features=fe, image_score=0.5)

        # With lower text weight and image=0.5, new score should differ
        assert result_new["final_score"] != result_old["final_score"]

    def test_image_zero_reduces_final(self):
        """image_score=0 should reduce final compared to old formula."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        fe = {"keywords": ["坚果", "零食"], "category": "食品",
              "weight_value": 0.0, "weight_unit": "", "package": "", "target": ""}

        result_old = fusion.calculate(text_score=0.8, query_features=fe,
                                      candidate_features=fe)
        result_new = fusion.calculate(text_score=0.8, query_features=fe,
                                      candidate_features=fe, image_score=0.0)

        assert result_new["final_score"] < result_old["final_score"]

    def test_existing_tests_still_compatible(self):
        """Old call pattern (3 args) still works and uses old formula."""
        from app.matching.fusion_matcher import FusionMatcher

        fusion = FusionMatcher()
        empty_fe = {"keywords": [], "category": "", "weight_value": 0.0,
                    "weight_unit": "", "package": "", "target": ""}

        result = fusion.calculate(0.5, empty_fe, empty_fe)
        assert result["final_score"] == 0.3  # 0.5*0.6 + 0.0*0.4
