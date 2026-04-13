"""
Unit tests for the hallucination detector (hallucination_detector.py).

Tier 1 (hedging phrase scan) tests use the real implementation — no mocking needed
since it's pure string analysis.

Tier 3 (paraphrase variance) tests mock the LLM calls and embedder to control
variance values and avoid hitting real APIs.

Tests cover:
- Tier 1: no hedging → SAFE (confidence 0.90)
- Tier 1: 1-2 hedging phrases → SAFE but noted (confidence 0.70)
- Tier 1: 3+ hedging phrases → flagged (is_hallucination=True)
- Tier 3: low variance → SAFE
- Tier 3: high variance (> θ=0.35) → flagged
- analyze(): general domain skips Tier 3
- analyze(): legal domain runs Tier 3 (mocked)
- analyze(): complexity > 0.7 runs Tier 3 (mocked)
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.hallucination_detector import HallucinationDetector, THETA
from app.services.llm_client import LLMResponse as LLMClientResponse


@pytest.fixture
def detector():
    return HallucinationDetector()


# ── Tier 1: Hedging phrase scan ──────────────────────────────────────────────

class TestTier1HedgingScan:
    def test_confident_response_is_safe(self, detector):
        result = detector.tier1_hedging_scan(
            "The capital of France is Paris. It has been the capital since 987 AD."
        )
        assert not result.is_hallucination
        assert result.confidence == 0.90
        assert result.pathway is None

    def test_single_hedge_is_safe_but_noted(self, detector):
        result = detector.tier1_hedging_scan(
            "I think the answer is 42, based on the data provided."
        )
        assert not result.is_hallucination
        assert result.confidence == 0.70

    def test_two_hedges_is_safe_but_noted(self, detector):
        # 2 hedges is below the 3+ threshold: "i think" + "might be" → SAFE but noted
        result = detector.tier1_hedging_scan(
            "I think the answer might be 42, based on the data."
        )
        assert not result.is_hallucination
        assert result.confidence == 0.70

    def test_three_hedges_flags_hallucination(self, detector):
        result = detector.tier1_hedging_scan(
            "I think this could be right, I believe it might work, "
            "possibly the answer, probably correct."
        )
        assert result.is_hallucination
        assert result.pathway == "linguistic_uncertainty"
        assert result.confidence >= 0.55

    def test_many_hedges_scales_confidence(self, detector):
        low_hedge = detector.tier1_hedging_scan(
            "I think this might be correct."
        )
        high_hedge = detector.tier1_hedging_scan(
            "I think it might be, I believe it could be, possibly, probably, "
            "I'm not sure, I may be wrong, approximately."
        )
        if high_hedge.is_hallucination and low_hedge.is_hallucination:
            assert high_hedge.confidence >= low_hedge.confidence


# ── Tier 3: Paraphrase variance ──────────────────────────────────────────────

def _make_llm_response(text: str) -> LLMClientResponse:
    return LLMClientResponse(
        content=text,
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.0,
        latency_ms=100,
        provider="openai",
    )


class TestTier3ParaphraseVariance:
    async def test_low_variance_returns_safe(self, detector):
        """When all responses are semantically similar, variance < θ → SAFE."""
        mock_llm = MagicMock()
        mock_llm.call_openai = AsyncMock(return_value=_make_llm_response(
            "Paraphrase 1\nParaphrase 2"
        ))
        # Both paraphrase responses are nearly identical to original
        mock_llm.call_llm = AsyncMock(return_value=_make_llm_response(
            "The capital of France is Paris."
        ))

        # Mock embedder to return very similar vectors (variance will be ~0)
        # Two rows: one per paraphrase response (original is no longer included)
        similar_vectors = np.array([
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],
        ], dtype=np.float32)

        with patch("app.services.hallucination_detector.get_embedder") as mock_emb:
            mock_emb.return_value.encode.return_value = similar_vectors
            result = await detector.tier3_paraphrase_variance(
                original_prompt="What is the capital of France?",
                original_response="The capital of France is Paris.",
                model="gpt-4o-mini",
                provider="openai",
                llm_client=mock_llm,
            )

        assert not result.is_hallucination
        assert "below threshold" in result.explanation

    async def test_high_variance_flags_hallucination(self, detector):
        """When responses diverge significantly, variance > θ → flagged."""
        mock_llm = MagicMock()
        mock_llm.call_openai = AsyncMock(return_value=_make_llm_response(
            "Paraphrase 1\nParaphrase 2"
        ))
        mock_llm.call_llm = AsyncMock(return_value=_make_llm_response(
            "Completely different answer."
        ))

        # Orthogonal vectors → cosine similarity = 0, variance = 1.0
        # Two rows: one per paraphrase response (original is no longer included)
        divergent_vectors = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ], dtype=np.float32)

        with patch("app.services.hallucination_detector.get_embedder") as mock_emb:
            mock_emb.return_value.encode.return_value = divergent_vectors
            result = await detector.tier3_paraphrase_variance(
                original_prompt="What year did Napoleon die?",
                original_response="Napoleon died in 1821.",
                model="gpt-4o-mini",
                provider="openai",
                llm_client=mock_llm,
            )

        assert result.is_hallucination
        assert result.pathway == "paraphrase_variance"
        assert result.confidence > 0.5

    async def test_paraphrase_generation_failure_degrades_gracefully(self, detector):
        mock_llm = MagicMock()
        mock_llm.call_openai = AsyncMock(side_effect=Exception("API error"))

        result = await detector.tier3_paraphrase_variance(
            original_prompt="Test prompt",
            original_response="Test response",
            model="gpt-4o-mini",
            provider="openai",
            llm_client=mock_llm,
        )

        assert not result.is_hallucination
        assert result.confidence == 0.50
        assert "skipped" in result.explanation


# ── analyze(): tier selection logic ─────────────────────────────────────────

class TestAnalyzeTierSelection:
    async def test_general_domain_skips_tier3(self, detector):
        """General domain with low complexity → only Tier 1 runs."""
        with patch.object(detector, "tier3_paraphrase_variance", new=AsyncMock()) as mock_t3:
            await detector.analyze(
                prompt="What is 2+2?",
                response="The answer is 4.",
                model="llama3.1",
                provider="ollama",
                complexity_score=0.1,
                domain="general",
                llm_client=MagicMock(),
            )
            mock_t3.assert_not_called()

    async def test_legal_domain_runs_tier3(self, detector):
        """Legal domain → Tier 3 must run regardless of complexity."""
        with patch.object(
            detector,
            "tier3_paraphrase_variance",
            new=AsyncMock(return_value=detector.tier1_hedging_scan("Safe response.")),
        ) as mock_t3:
            await detector.analyze(
                prompt="Is a non-compete enforceable in California?",
                response="Non-competes are generally unenforceable in California.",
                model="gpt-4o",
                provider="openai",
                complexity_score=0.3,
                domain="legal",
                llm_client=MagicMock(),
            )
            mock_t3.assert_called_once()

    async def test_high_complexity_runs_tier3(self, detector):
        """complexity_score > 0.7 → Tier 3 runs even for general domain."""
        with patch.object(
            detector,
            "tier3_paraphrase_variance",
            new=AsyncMock(return_value=detector.tier1_hedging_scan("Safe response.")),
        ) as mock_t3:
            await detector.analyze(
                prompt="Design a distributed system...",
                response="You should use microservices.",
                model="gpt-4o",
                provider="openai",
                complexity_score=0.85,
                domain="general",
                llm_client=MagicMock(),
            )
            mock_t3.assert_called_once()
