"""
Unit tests for the semantic cache (cache.py).

Uses a fresh SemanticCache instance per test (not the module singleton)
so tests are isolated and don't pollute each other.

Tests cover:
- Cache miss on empty store
- Cache hit for identical prompt (similarity ≈ 1.0)
- Cache hit for semantically similar prompt (paraphrase)
- Cache miss for dissimilar prompt
- Size property tracking
"""

import pytest
from app.services.cache import SemanticCache


@pytest.fixture
def cache():
    """Fresh SemanticCache instance for each test (shares the module embedder)."""
    return SemanticCache(threshold=0.85)


FAKE_RESPONSE = {
    "response": "Paris is the capital of France.",
    "model_used": "gpt-4o-mini",
    "provider": "openai",
    "complexity_score": 0.15,
    "routing_decision": {"model": "gpt-4o-mini", "reason": "test", "confidence": 0.8},
    "cost": 0.000010,
    "latency_ms": 500,
}


class TestCacheMiss:
    def test_empty_cache_returns_none(self, cache):
        result = cache.lookup("What is the capital of France?")
        assert result is None

    def test_size_starts_at_zero(self, cache):
        assert cache.size == 0


class TestCacheHit:
    def test_identical_prompt_hits(self, cache):
        prompt = "What is the capital of France?"
        cache.add(prompt, FAKE_RESPONSE)
        result = cache.lookup(prompt)
        assert result is not None
        assert result["response"] == FAKE_RESPONSE["response"]

    def test_size_increments_after_add(self, cache):
        cache.add("Test prompt one", FAKE_RESPONSE)
        assert cache.size == 1
        cache.add("Test prompt two", FAKE_RESPONSE)
        assert cache.size == 2

    def test_semantically_similar_prompt_hits(self, cache):
        cache.add(
            "What is the capital city of France?",
            FAKE_RESPONSE,
        )
        # Paraphrase — should exceed 0.85 cosine similarity
        result = cache.lookup("What is France's capital?")
        assert result is not None, (
            "Paraphrase of a cached prompt should hit the cache at threshold 0.85"
        )


class TestCacheMissOnDissimilar:
    def test_unrelated_prompt_misses(self, cache):
        cache.add("What is the capital of France?", FAKE_RESPONSE)
        result = cache.lookup("Explain quantum computing and its applications.")
        assert result is None, (
            "Unrelated prompt should not hit a cache entry about France's capital"
        )
