"""
Shared sentence-transformer embedder singleton.

Both SemanticCache and HallucinationDetector need all-MiniLM-L6-v2.
Loading it twice wastes ~90MB RAM. This module ensures a single instance
is created lazily and shared across the process.
"""

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_embedder: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    """Return the shared SentenceTransformer instance, loading it on first call."""
    global _embedder
    if _embedder is None:
        logger.info("Embedder: loading all-MiniLM-L6-v2 (first use)...")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedder: ready")
    return _embedder
