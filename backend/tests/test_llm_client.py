"""
Unit tests for the vLLM provider in LLMClient.

Tests:
  - call_vllm returns a correct LLMResponse when the server responds.
  - Router falls back to groq when _vllm_available() returns False.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from app.services.llm_client import LLMClient, LLMResponse


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_openai_chat_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    """Build a minimal object that looks like openai ChatCompletion."""
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


# ── call_vllm ────────────────────────────────────────────────────────────────

class TestCallVllm:
    def test_call_vllm_success(self):
        """call_vllm maps a vLLM OpenAI-compatible response to LLMResponse correctly."""
        fake_response = _make_openai_chat_response("Hello from vLLM!", 12, 8)

        mock_completions = AsyncMock(return_value=fake_response)

        client = LLMClient.__new__(LLMClient)
        client.vllm_client = MagicMock()
        client.vllm_client.chat.completions.create = mock_completions

        import asyncio
        messages = [{"role": "user", "content": "hi"}]
        result: LLMResponse = asyncio.run(
            client.call_vllm(
                model="meta-llama/Llama-3.1-8B-Instruct",
                messages=messages,
                temperature=0.0,
                max_tokens=256,
            )
        )

        assert result.provider == "vllm"
        assert result.content == "Hello from vLLM!"
        assert result.input_tokens == 12
        assert result.output_tokens == 8
        assert result.cost_usd == 0.0
        assert result.latency_ms >= 0
        mock_completions.assert_awaited_once()

    def test_call_vllm_raises_when_client_not_initialized(self):
        """call_vllm raises when vllm_client is None (VLLM_BASE_URL not set).

        tenacity wraps the ValueError in RetryError after 3 attempts, so we
        assert on the base Exception class and check the cause.
        """
        client = LLMClient.__new__(LLMClient)
        client.vllm_client = None

        import asyncio
        from tenacity import RetryError

        with pytest.raises((ValueError, RetryError)):
            asyncio.run(
                client.call_vllm(
                    model="meta-llama/Llama-3.1-8B-Instruct",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )


# ── router vLLM override ─────────────────────────────────────────────────────

class TestRouterVllmOverride:
    def test_vllm_takes_priority_over_groq_when_available(self):
        """
        When _vllm_available() returns True, a groq-routed request is redirected
        to the vLLM provider and the state reflects the new model/provider.
        """
        import asyncio
        from app.agents.router import RouterAgent

        agent = RouterAgent.__new__(RouterAgent)
        agent._vllm_reachable = True   # pre-cache: vLLM is up
        agent._ollama_reachable = False

        fake_vllm_resp = LLMResponse(
            content="vLLM answer",
            model="meta-llama/Llama-3.1-8B-Instruct",
            input_tokens=5,
            output_tokens=10,
            cost_usd=0.0,
            latency_ms=50,
            provider="vllm",
        )

        state = {
            "prompt": "What is 2+2?",
            "context": None,
            "forced_model": None,
            "complexity_score": 0.1,
            "model": "llama-3.1-8b-instant",
            "provider": "groq",
            "reasoning": "cheap query → llama-3.1-8b-instant",
            "confidence": 0.9,
            "response": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": None,
        }

        with patch("app.agents.router.llm_client.call_vllm", new=AsyncMock(return_value=fake_vllm_resp)):
            result = asyncio.run(agent._call_llm_node(state))

        assert result["provider"] == "vllm"
        assert result["model"] == "meta-llama/Llama-3.1-8B-Instruct"
        assert result["cost_usd"] == 0.0
        assert "vLLM GPU" in result["reasoning"]

    def test_groq_used_when_vllm_unavailable(self):
        """
        When _vllm_available() returns False and _ollama_available() is False,
        the router calls groq directly.
        """
        import asyncio
        from app.agents.router import RouterAgent

        agent = RouterAgent.__new__(RouterAgent)
        agent._vllm_reachable = False
        agent._ollama_reachable = False

        fake_groq_resp = LLMResponse(
            content="groq answer",
            model="llama-3.1-8b-instant",
            input_tokens=5,
            output_tokens=10,
            cost_usd=0.0,
            latency_ms=80,
            provider="groq",
        )

        state = {
            "prompt": "What is 2+2?",
            "context": None,
            "forced_model": None,
            "complexity_score": 0.1,
            "model": "llama-3.1-8b-instant",
            "provider": "groq",
            "reasoning": "cheap query → groq",
            "confidence": 0.9,
            "response": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": None,
        }

        with patch("app.agents.router.llm_client.call_llm", new=AsyncMock(return_value=fake_groq_resp)):
            result = asyncio.run(agent._call_llm_node(state))

        assert result["provider"] == "groq"
        assert result["model"] == "llama-3.1-8b-instant"
