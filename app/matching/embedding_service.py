"""EmbeddingService — lightweight text-to-vector conversion (Phase 34).

Converts Chinese product titles into fixed-dimension dense vectors using
jieba word segmentation + character n-gram feature hashing. No large
models required.

Algorithm:
    1. jieba word segmentation
    2. Character unigrams/bigrams/trigrams (supplementary)
    3. Feature hashing to fixed dimension
    4. TF weighting
    5. L2 normalization
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any


class EmbeddingService:
    """Lightweight text embedding for product matching.

    Converts Chinese product titles into fixed-dimension dense vectors
    suitable for cosine similarity search. Uses jieba + n-gram hashing.

    Usage::

        service = EmbeddingService(dim=512)
        vec = service.encode_text("三只松鼠坚果礼盒装")
        # len(vec) == 512, L2-normalized

        vec2 = service.encode_product(supplier_product)
        # combines title + category + shop_name
    """

    def __init__(self, dim: int = 512) -> None:
        """Initialize EmbeddingService.

        Args:
            dim: Fixed output vector dimension (must be positive).
        """
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self.dim = dim

    # ── Public API ────────────────────────────────────────────

    def encode_text(self, text: str) -> list[float]:
        """Convert text to a fixed-dimension vector.

        Args:
            text: Input text (e.g., Chinese product title).

        Returns:
            Dense float vector of length ``self.dim``, L2-normalized.
            Returns zero vector for empty/whitespace input.
        """
        if not text or not text.strip():
            return [0.0] * self.dim

        # Step 1: jieba word segmentation
        import jieba
        words = list(jieba.cut(text.strip()))
        words = [w.strip() for w in words if w.strip()]

        # Step 2: character n-grams (supplementary features)
        clean = re.sub(r"\s+", "", text.strip())
        ngrams: list[str] = []
        for n in (1, 2, 3):
            for i in range(len(clean) - n + 1):
                ngrams.append(clean[i : i + n])

        # Step 3: combine and hash to indices
        all_tokens = words + ngrams
        indices: list[int] = []
        for token in all_tokens:
            h = hashlib.md5(token.encode("utf-8")).hexdigest()
            idx = int(h, 16) % self.dim
            indices.append(idx)

        # Step 4: TF weighting
        counter = Counter(indices)
        max_tf = max(counter.values()) if counter else 1
        vector = [0.0] * self.dim
        for idx, count in counter.items():
            vector[idx] = count / max_tf

        # Step 5: L2 normalization
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def encode_product(self, product: Any) -> list[float]:
        """Convert a supplier product to a vector.

        Combines title + category + shop_name for richer representation.

        Args:
            product: SupplierProductDB or similar object with ``.title``.

        Returns:
            Dense float vector of length ``self.dim``.
        """
        parts = [getattr(product, "title", "")]

        # Add category if available
        if hasattr(product, "category") and getattr(product, "category"):
            parts.append(str(getattr(product, "category")))

        # Add shop name for context
        if hasattr(product, "shop_name") and getattr(product, "shop_name"):
            parts.append(str(getattr(product, "shop_name")))

        combined = " ".join(p for p in parts if p)
        return self.encode_text(combined)
