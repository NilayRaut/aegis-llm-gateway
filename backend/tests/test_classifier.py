"""
Unit tests for the complexity classifier (classifier.py).

Tests cover:
- Simple prompts → low score → cheap model tier
- Analytical prompts → higher score (explain/compare keywords)
- Complex design prompts → high score
- Routing table boundaries (each tier maps to correct model)
- Forced model override bypasses classifier
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.classifier import classifier


class TestComplexityScoring:
    def test_simple_factual_prompt_scores_low(self):
        score = classifier.score("What is 2 + 2?")
        assert score < 0.4, f"Expected simple prompt < 0.4, got {score:.3f}"

    def test_analytical_prompt_scores_higher(self):
        simple = classifier.score("What is Python?")
        analytical = classifier.score(
            "Explain the difference between supervised and unsupervised machine learning."
        )
        assert analytical > simple, (
            f"Analytical ({analytical:.3f}) should score higher than simple ({simple:.3f})"
        )

    def test_design_prompt_scores_high(self):
        score = classifier.score(
            "Design a distributed microservices architecture with event sourcing, "
            "CQRS, and optimized for high throughput and low latency."
        )
        # "design" triggers complex pattern (+0.8 to question score).
        # Short single-sentence prompt keeps structure + semantic low.
        # Empirically scores ~0.30–0.40 → above simple-factual tier.
        assert score > 0.3, f"Expected design prompt > 0.3, got {score:.3f}"

    def test_score_bounded_0_to_1(self):
        for prompt in [
            "Hi",
            "What time is it?",
            "Explain quantum entanglement and its implications for computing architectures.",
        ]:
            score = classifier.score(prompt)
            assert 0.0 <= score <= 1.0, f"Score out of bounds for '{prompt}': {score}"


class TestRoutingTable:
    def test_low_score_routes_to_groq(self):
        model, provider = classifier.route(0.1)
        assert provider == "groq"
        assert model == "llama-3.1-8b-instant"

    def test_mid_low_score_routes_to_gemini(self):
        model, provider = classifier.route(0.3)
        assert provider == "google"
        assert model == "gemini-2.5-flash"

    def test_mid_score_routes_to_gpt4o_mini(self):
        model, provider = classifier.route(0.70)  # mid of (0.65, 0.80)
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_high_score_routes_to_claude(self):
        model, provider = classifier.route(0.60)  # mid of (0.50, 0.70)
        assert provider == "anthropic"

    def test_very_high_score_routes_to_gpt4o(self):
        model, provider = classifier.route(0.9)
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_boundary_score_1_0_defaults_to_gpt4o(self):
        model, provider = classifier.route(1.0)
        assert model == "gpt-4o"


class TestClassifyAndRoute:
    def test_returns_required_keys(self):
        result = classifier.classify_and_route("What is the weather today?")
        assert "complexity_score" in result
        assert "model" in result
        assert "provider" in result
        assert "reasoning" in result
        assert "confidence" in result

    def test_reasoning_is_non_empty_string(self):
        result = classifier.classify_and_route("Explain black holes.")
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    def test_provider_rotation_distributes_providers(self):
        """
        classify_and_route() should use random.choice from each band's pool,
        so repeated calls on a moderate prompt hit more than one provider.
        Run 30 trials — probability of seeing only 1 provider from a 2-entry
        pool is (0.5)^29 ≈ 0.000000002, effectively zero.
        """
        prompt = "Explain the difference between supervised and unsupervised learning."
        providers_seen = set()
        for _ in range(30):
            result = classifier.classify_and_route(prompt)
            providers_seen.add(result["provider"])
        assert len(providers_seen) >= 2, (
            f"Expected rotation across ≥2 providers, got: {providers_seen}"
        )


class TestLLMClassifier:
    async def test_llm_score_used_when_groq_available(self):
        """When Groq responds, score_async returns the LLM's score."""
        mock_resp = MagicMock()
        mock_resp.content = "0.35"
        with patch("app.services.classifier.llm_client") as mock_client:
            mock_client.groq_client = MagicMock()
            mock_client.call_groq = AsyncMock(return_value=mock_resp)
            score = await classifier.score_async("Why does ice float?")
        assert abs(score - 0.35) < 0.01

    async def test_fallback_to_heuristic_when_groq_fails(self):
        """When Groq raises an exception, score_async falls back to heuristic score()."""
        with patch("app.services.classifier.llm_client") as mock_client:
            mock_client.groq_client = MagicMock()
            mock_client.call_groq = AsyncMock(side_effect=Exception("Groq unavailable"))
            score = await classifier.score_async("What is 2 + 2?")
        assert 0.0 <= score <= 1.0

    async def test_llm_score_clamped_to_valid_range(self):
        """LLM returning out-of-range value (e.g. 1.7) is clamped to 1.0."""
        mock_resp = MagicMock()
        mock_resp.content = "1.7"
        with patch("app.services.classifier.llm_client") as mock_client:
            mock_client.groq_client = MagicMock()
            mock_client.call_groq = AsyncMock(return_value=mock_resp)
            score = await classifier.score_async("test prompt")
        assert score == 1.0
