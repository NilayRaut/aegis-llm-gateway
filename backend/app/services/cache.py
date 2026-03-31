"""
Semantic Cache — in-memory cache using sentence-transformer embeddings.

Uses cosine similarity at threshold 0.85 (not 0.95 — that gives <1% hit rate).
Reuses the same model architecture as classifier.py (all-MiniLM-L6-v2)
but as a separate instance to avoid coupling.

Cache is in-memory only (no Redis needed for demo).
Resets on server restart — this is intentional for the demo.
"""

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    In-memory semantic cache backed by sentence-transformers + numpy cosine similarity.

    threshold=0.85 means: if two prompts are ≥85% semantically similar,
    treat them as the same question and return the cached answer.

    Example: "What time is it in Tokyo?" and "What is the current time in Tokyo?"
    would both hit the same cache entry.
    """

    def __init__(self, threshold: float = 0.85) -> None:
        logger.info("SemanticCache: loading sentence-transformer model...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.store: list[dict] = []
        # Each entry: {"embedding": np.ndarray, "response_obj": dict, "prompt": str}
        self.threshold = threshold
        self._hits = 0
        self._misses = 0
        logger.info("SemanticCache: ready (threshold=%.2f)", threshold)

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors. Returns 0.0 if either is zero-norm."""
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def lookup(self, prompt: str) -> dict | None:
        """
        Check if a semantically similar prompt exists in cache.

        Returns the cached response_obj if similarity >= threshold, else None.
        Returns the first match found (not highest similarity — first is fine for demo).
        """
        if not self.store:
            self._misses += 1
            return None

        query_emb = self.model.encode(prompt)
        for entry in self.store:
            similarity = self._cosine(query_emb, entry["embedding"])
            if similarity >= self.threshold:
                self._hits += 1
                logger.info(
                    "Cache HIT (similarity=%.3f, hits=%d, misses=%d)",
                    similarity, self._hits, self._misses,
                )
                return entry["response_obj"]

        self._misses += 1
        logger.debug("Cache MISS (hits=%d, misses=%d)", self._hits, self._misses)
        return None

    def add(self, prompt: str, response_obj: dict) -> None:
        """Add a prompt+response to the cache."""
        emb = self.model.encode(prompt)
        self.store.append({
            "embedding": emb,
            "response_obj": response_obj,
            "prompt": prompt,
        })
        logger.debug("Cache ADD (store size=%d)", len(self.store))

    @property
    def size(self) -> int:
        return len(self.store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total * 100, 2) if total > 0 else 0.0


# Module-level singleton — model loads once at import time (cached on disk after first download)
semantic_cache = SemanticCache(threshold=0.85)
