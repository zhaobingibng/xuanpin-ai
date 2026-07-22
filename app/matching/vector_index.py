"""VectorIndex — in-memory cosine similarity search index (Phase 34).

Stores fixed-dimension vectors and supports add, delete, and top-k
similarity search. Pure Python implementation — no external dependencies.
"""

from __future__ import annotations

import math


class VectorIndex:
    """In-memory vector index with cosine similarity search.

    Stores fixed-dimension vectors and supports add, delete, and top-k
    similarity search. Pure Python implementation.

    Usage::

        index = VectorIndex()
        index.add(1, [0.1, 0.2, 0.3])
        index.add(2, [0.3, 0.1, 0.2])
        results = index.search([0.15, 0.25, 0.35], top_k=10)
        # [(1, 0.98), (2, 0.72), ...]
        index.delete(1)
    """

    def __init__(self) -> None:
        """Initialize empty vector index."""
        self._items: dict[int, list[float]] = {}

    # ── Public API ────────────────────────────────────────────

    def add(self, item_id: int, vector: list[float]) -> None:
        """Add or update a vector for the given item_id.

        Args:
            item_id: Unique identifier for the item.
            vector: Dense float vector.

        Raises:
            ValueError: If vector is None.
        """
        if vector is None:
            raise ValueError("vector cannot be None")
        self._items[item_id] = list(vector)

    def delete(self, item_id: int) -> bool:
        """Delete a vector from the index.

        Args:
            item_id: Identifier to remove.

        Returns:
            True if the item was found and deleted, False otherwise.
        """
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def search(
        self,
        query_vector: list[float],
        top_k: int = 100,
    ) -> list[tuple[int, float]]:
        """Search for top-k most similar items by cosine similarity.

        Args:
            query_vector: Query vector to search for.
            top_k: Maximum number of results to return. Must be >= 1.

        Returns:
            List of (item_id, similarity_score) tuples sorted by
            similarity descending. Empty list if index is empty or
            query_vector is None.
        """
        if query_vector is None:
            return []
        if top_k < 1:
            return []
        if not self._items:
            return []

        scores: list[tuple[int, float]] = []
        for item_id, item_vector in self._items.items():
            sim = self._cosine_similarity(query_vector, item_vector)
            scores.append((item_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    # ── Info ──────────────────────────────────────────────────

    def __len__(self) -> int:
        """Number of items in the index."""
        return len(self._items)

    def __contains__(self, item_id: int) -> bool:
        """Check if item_id exists in the index."""
        return item_id in self._items

    @property
    def item_ids(self) -> list[int]:
        """Return all item IDs in the index."""
        return list(self._items.keys())

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Similarity score in [0, 1] (assuming non-negative vectors).
            Returns 0.0 if either vector has zero norm.

        Raises:
            ValueError: If vectors have different dimensions.
        """
        if len(a) != len(b):
            raise ValueError(
                f"Vector dimension mismatch: {len(a)} vs {len(b)}"
            )

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)
