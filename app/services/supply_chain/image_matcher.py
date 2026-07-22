"""ImageSimilarityMatcher — perceptual image hashing for visual similarity.

Uses dHash (difference hash) for fast, lightweight image comparison.
No deep learning models required — works well for product images that
are visually similar (same product, different angles/crops).
"""

from __future__ import annotations

import hashlib
import io
from functools import lru_cache
from typing import Any

from loguru import logger

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ImageSimilarityMatcher:
    """Perceptual image similarity using dHash.

    dHash works by:
    1. Resize image to 9x8 grayscale
    2. Compare adjacent pixels (8x8 = 64 bits)
    3. Generate a 64-bit hash
    4. Compare hashes using hamming distance

    Usage::

        matcher = ImageSimilarityMatcher()
        score = matcher.compare_urls(url_a, url_b)
        hash_a = matcher.compute_hash_from_url(url_a)
    """

    # dHash parameters
    HASH_SIZE = 8  # 8x8 = 64 bit hash

    # Similarity thresholds
    SIMILAR_THRESHOLD = 0.7  # Above this = visually similar
    IDENTICAL_THRESHOLD = 0.9  # Above this = likely identical

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout
        self._hash_cache: dict[str, str] = {}

    def compute_dhash(self, image: "Image.Image") -> str:
        """Compute dHash for a PIL Image.

        Returns:
            16-character hex string (64-bit hash).
        """
        if not HAS_PIL:
            raise RuntimeError("Pillow not installed")

        # Resize to 9x8 grayscale
        resized = image.convert("L").resize((self.HASH_SIZE + 1, self.HASH_SIZE), Image.LANCZOS)
        pixels = list(resized.getdata())

        # Compare adjacent pixels
        bits = []
        for row in range(self.HASH_SIZE):
            for col in range(self.HASH_SIZE):
                left = pixels[row * (self.HASH_SIZE + 1) + col]
                right = pixels[row * (self.HASH_SIZE + 1) + col + 1]
                bits.append(1 if left > right else 0)

        # Convert bits to hex
        hash_int = 0
        for bit in bits:
            hash_int = (hash_int << 1) | bit

        return format(hash_int, f"0{self.HASH_SIZE * 2}x")

    def compute_hash_from_bytes(self, data: bytes) -> str | None:
        """Compute dHash from image bytes."""
        if not HAS_PIL:
            return None
        try:
            image = Image.open(io.BytesIO(data))
            return self.compute_dhash(image)
        except Exception as e:
            logger.debug("[ImageMatcher] Failed to decode image bytes: {}", e)
            return None

    def compute_hash_from_url(self, url: str) -> str | None:
        """Compute dHash from image URL (with caching).

        Downloads the image, computes hash, caches result.
        Returns None on failure.
        """
        if not url:
            return None

        # Check cache
        if url in self._hash_cache:
            return self._hash_cache[url]

        if not HAS_PIL:
            return None

        try:
            import httpx
            resp = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            resp.raise_for_status()
            image = Image.open(io.BytesIO(resp.content))
            hash_val = self.compute_dhash(image)
            self._hash_cache[url] = hash_val
            return hash_val
        except Exception as e:
            logger.debug("[ImageMatcher] Failed to download/compute hash for '{}': {}", url[:60], e)
            return None

    @staticmethod
    def hamming_distance(hash_a: str, hash_b: str) -> int:
        """Compute hamming distance between two hex hash strings."""
        if len(hash_a) != len(hash_b):
            return 64  # Max distance for different length hashes
        int_a = int(hash_a, 16)
        int_b = int(hash_b, 16)
        xor = int_a ^ int_b
        return bin(xor).count("1")

    @staticmethod
    def similarity_from_hamming(distance: int, hash_size: int = 8) -> float:
        """Convert hamming distance to similarity score (0-1)."""
        max_bits = hash_size * hash_size  # 64 for 8x8
        if max_bits == 0:
            return 0.0
        return 1.0 - (distance / max_bits)

    def compare_hashes(self, hash_a: str, hash_b: str) -> float:
        """Compare two hashes and return similarity score (0-1)."""
        distance = self.hamming_distance(hash_a, hash_b)
        return self.similarity_from_hamming(distance, self.HASH_SIZE)

    def compare_urls(self, url_a: str, url_b: str) -> float:
        """Compare two image URLs and return similarity score (0-1).

        Returns 0.0 if either URL fails to download/parse.
        """
        if not url_a or not url_b:
            return 0.0

        hash_a = self.compute_hash_from_url(url_a)
        hash_b = self.compute_hash_from_url(url_b)

        if hash_a is None or hash_b is None:
            return 0.0

        return self.compare_hashes(hash_a, hash_b)

    def compare_bytes_with_url(
        self, image_bytes: bytes, url: str
    ) -> float:
        """Compare local image bytes with a remote URL image."""
        if not url:
            return 0.0

        hash_local = self.compute_hash_from_bytes(image_bytes)
        if hash_local is None:
            return 0.0

        hash_remote = self.compute_hash_from_url(url)
        if hash_remote is None:
            return 0.0

        return self.compare_hashes(hash_local, hash_remote)

    def clear_cache(self) -> None:
        """Clear the URL hash cache."""
        self._hash_cache.clear()
