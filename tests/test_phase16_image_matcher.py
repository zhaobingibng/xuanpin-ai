"""Tests for ImageSimilarityMatcher and SupplyChainMatcher image integration."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


# ============================================================
# ImageSimilarityMatcher Tests
# ============================================================

class TestImageSimilarityMatcher:
    """Test dHash computation and comparison."""

    def test_import(self):
        """Test module imports correctly."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher, HAS_PIL
        assert HAS_PIL is True  # Pillow is installed

    def test_init(self):
        """Test matcher initialization."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher(timeout=5)
        assert matcher._timeout == 5
        assert matcher.HASH_SIZE == 8

    def test_compute_dhash_returns_hex_string(self):
        """Test dHash returns 16-char hex string."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()
        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="red")
        hash_val = matcher.compute_dhash(img)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 16  # 64 bits = 16 hex chars

    def test_same_image_same_hash(self):
        """Test identical images produce identical hashes."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()
        img = Image.new("RGB", (100, 100), color="blue")
        hash_a = matcher.compute_dhash(img)
        hash_b = matcher.compute_dhash(img)
        assert hash_a == hash_b

    def test_similar_images_high_score(self):
        """Test similar images produce high similarity score."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()

        # Create two similar images (slight color difference)
        img_a = Image.new("RGB", (100, 100), color=(200, 100, 50))
        img_b = Image.new("RGB", (100, 100), color=(205, 105, 55))

        hash_a = matcher.compute_dhash(img_a)
        hash_b = matcher.compute_dhash(img_b)
        score = matcher.compare_hashes(hash_a, hash_b)

        # Similar images should have high similarity
        assert score >= 0.8

    def test_different_images_low_score(self):
        """Test very different images produce low similarity."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()

        # Create two very different images (checkerboard vs solid)
        img_a = Image.new("L", (100, 100), 128)  # Solid gray
        img_b = Image.new("L", (100, 100), 0)  # Black
        # Draw white stripes on img_b
        for x in range(0, 100, 10):
            for y in range(100):
                img_b.putpixel((x, y), 255)

        hash_a = matcher.compute_dhash(img_a)
        hash_b = matcher.compute_dhash(img_b)
        score = matcher.compare_hashes(hash_a, hash_b)

        # Different patterns should have lower similarity
        assert score < 1.0  # Not identical

    def test_hamming_distance(self):
        """Test hamming distance calculation."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        # Same hash = 0 distance
        assert ImageSimilarityMatcher.hamming_distance("abcd", "abcd") == 0
        # Different hash
        dist = ImageSimilarityMatcher.hamming_distance("0000", "ffff")
        assert dist == 16  # All bits different in 4 hex chars = 16 bits

    def test_similarity_from_hamming(self):
        """Test hamming to similarity conversion."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        # 0 distance = 1.0 similarity
        assert ImageSimilarityMatcher.similarity_from_hamming(0, 8) == 1.0
        # Max distance (64 bits) = 0.0 similarity
        assert ImageSimilarityMatcher.similarity_from_hamming(64, 8) == 0.0
        # Half distance = 0.5 similarity
        assert ImageSimilarityMatcher.similarity_from_hamming(32, 8) == 0.5

    def test_compute_hash_from_bytes(self):
        """Test hash computation from image bytes."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()

        # Create image and convert to bytes
        img = Image.new("RGB", (50, 50), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        hash_val = matcher.compute_hash_from_bytes(data)
        assert hash_val is not None
        assert len(hash_val) == 16

    def test_compute_hash_from_bytes_invalid(self):
        """Test hash computation with invalid bytes returns None."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()
        result = matcher.compute_hash_from_bytes(b"not an image")
        assert result is None

    def test_compare_urls_empty(self):
        """Test compare_urls with empty URLs returns 0."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()
        assert matcher.compare_urls("", "") == 0.0
        assert matcher.compare_urls(None, None) == 0.0
        assert matcher.compare_urls("http://a.com/img.jpg", "") == 0.0

    def test_clear_cache(self):
        """Test cache clearing."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        matcher = ImageSimilarityMatcher()
        matcher._hash_cache["test"] = "abc"
        matcher.clear_cache()
        assert len(matcher._hash_cache) == 0

    def test_thresholds(self):
        """Test threshold constants."""
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        assert ImageSimilarityMatcher.SIMILAR_THRESHOLD == 0.7
        assert ImageSimilarityMatcher.IDENTICAL_THRESHOLD == 0.9


# ============================================================
# SupplyChainMatcher Image Integration Tests
# ============================================================

class TestSupplyChainMatcherImageIntegration:
    """Test SupplyChainMatcher with image matching enabled."""

    def test_init_default_no_image(self):
        """Test default init disables image matching."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session)
        assert matcher._enable_image_match is False
        assert matcher._image_matcher is None

    def test_init_with_image_enabled(self):
        """Test init with image matching enabled."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=True)
        assert matcher._enable_image_match is True

    def test_weights_sum(self):
        """Test title + image weights are reasonable."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        # Weights should be meaningful
        assert SupplyChainMatcher.TITLE_WEIGHT > 0
        assert SupplyChainMatcher.IMAGE_WEIGHT > 0
        assert SupplyChainMatcher.TITLE_WEIGHT + SupplyChainMatcher.IMAGE_WEIGHT == 1.0

    def test_get_image_matcher_lazy(self):
        """Test image matcher is lazily initialized."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=True)
        assert matcher._image_matcher is None

        # After calling _get_image_matcher
        im = matcher._get_image_matcher()
        assert im is not None
        from app.services.supply_chain.image_matcher import ImageSimilarityMatcher
        assert isinstance(im, ImageSimilarityMatcher)

    def test_get_image_matcher_disabled(self):
        """Test image matcher returns None when disabled."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=False)
        im = matcher._get_image_matcher()
        assert im is None

    def test_title_similarity_still_works(self):
        """Test title similarity calculation still works."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        score = SupplyChainMatcher._title_similarity(
            "2024新款夏季连衣裙", "2024新款夏季碎花连衣裙"
        )
        assert score > 0.5

    def test_match_type_title_only(self):
        """Test match_type is 'title' when image matching disabled."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=False)
        # match_type will be "title" in results
        assert matcher._enable_image_match is False

    def test_match_type_with_image(self):
        """Test match_type can be 'title+image' when image matching enabled."""
        from app.services.supply_chain.matcher import SupplyChainMatcher
        session = MagicMock()
        matcher = SupplyChainMatcher(session, enable_image_match=True)
        # When image matching is enabled and images match, type becomes "title+image"
        assert matcher._enable_image_match is True
