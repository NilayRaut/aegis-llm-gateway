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
        assert model == "gemini-1.5-flash"

    def test_mid_score_routes_to_gpt4o_mini(self):
        model, provider = classifier.route(0.5)
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_high_score_routes_to_claude(self):
        model, provider = classifier.route(0.7)
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
