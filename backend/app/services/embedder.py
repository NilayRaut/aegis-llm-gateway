"""
Shared embedder singleton.

Both SemanticCache and HallucinationDetector need all-MiniLM-L6-v2.
Uses fastembed (ONNX Runtime) instead of sentence-transformers (PyTorch)
to stay within the 512MB RAM limit on Render's free tier (~100MB vs ~400MB).
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

_embedder = None


class _EmbedderWrapper:
    """Thin wrapper around fastembed.TextEmbedding preserving the .encode() interface."""

    def __init__(self) -> None:
        # Lazy import: defer onnxruntime load to first request, not app startup.
        # This keeps startup memory well under Render's 512MB free-tier limit.
        from fastembed import TextEmbedding
        logger.info("Embedder: loading all-MiniLM-L6-v2 via fastembed (ONNX)...")
        self._model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("Embedder: ready")

    def encode(self, texts, normalize_embeddings: bool = True) -> np.ndarray:
        """
        Encode one string or a list of strings into embeddings.

        - Single string  → 1D numpy array  (shape: [384])
        - List of strings → 2D numpy array (shape: [n, 384])

        fastembed normalizes by default (L2 norm), so normalize_embeddings
        is accepted for interface compatibility but has no effect.
        """
        if isinstance(texts, str):
            return list(self._model.embed([texts]))[0]
        return np.array(list(self._model.embed(texts)))


def get_embedder() -> _EmbedderWrapper:
    """Return the shared embedder instance, loading it on first call."""
    global _embedder
    if _embedder is None:
        _embedder = _EmbedderWrapper()
    return _embedder
