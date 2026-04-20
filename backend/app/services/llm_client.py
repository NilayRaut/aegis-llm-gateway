"""
LLM Client Service - Unified interface for all LLM providers
Supports: OpenAI (GPT-4o, GPT-4o-mini), Anthropic (Claude Haiku), Google (Gemini Flash), Ollama (Llama-3)
"""

import os
import asyncio
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import logging
from dotenv import load_dotenv

# Load environment variables before initializing clients
load_dotenv()

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ollama is optional — only used for local dev. Not installed in production.
try:
    from ollama import AsyncClient as _OllamaAsyncClient
    _OLLAMA_SDK = True
except ImportError:
    _OllamaAsyncClient = None  # type: ignore[assignment,misc]
    _OLLAMA_SDK = False

from app.utils.cost_calculator import calculate_cost

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider"""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    provider: str


class LLMClient:
    """
    Unified client for all LLM providers
    Handles authentication, retries, and cost tracking
    """
    
    # Cost per 1M tokens (as of 2024)
    COST_PER_1M = {
        # OpenAI
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},

        # Anthropic
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},

        # Google
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},

        # Ollama (local, free)
        "llama3.1": {"input": 0.0, "output": 0.0},

        # Groq (free tier)
        "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
    }
    
    def __init__(self):
        """Initialize all LLM clients"""
        self.openai_client = None
        self.anthropic_client = None
        self.google_client = None
        self.ollama_client = None
        self.groq_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize clients based on available API keys"""
        # OpenAI
        if openai_key := os.getenv("OPENAI_API_KEY"):
            self.openai_client = AsyncOpenAI(api_key=openai_key)
            logger.info("OpenAI client initialized")
        else:
            logger.warning("OPENAI_API_KEY not found, OpenAI calls will fail")
        
        # Anthropic
        if anthropic_key := os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = AsyncAnthropic(api_key=anthropic_key)
            logger.info("Anthropic client initialized")
        else:
            logger.warning("ANTHROPIC_API_KEY not found, Anthropic calls will fail")
        
        # Google
        if google_key := os.getenv("GOOGLE_API_KEY"):
            self.google_client = genai.Client(api_key=google_key)
            logger.info("Google GenAI client initialized")
        else:
            self.google_client = None
            logger.warning("GOOGLE_API_KEY not found, Gemini calls will fail")
        
        # Ollama (local, optional)
        if _OLLAMA_SDK:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.ollama_client = _OllamaAsyncClient(host=ollama_url)
            logger.info(f"Ollama client initialized at {ollama_url}")
        else:
            self.ollama_client = None
            logger.info("Ollama SDK not installed — local Ollama disabled (install 'ollama>=0.2.0' for local dev)")

        # Groq
        if groq_key := os.getenv("GROQ_API_KEY"):
            from groq import AsyncGroq
            self.groq_client = AsyncGroq(api_key=groq_key)
            logger.info("Groq client initialized")
        else:
            logger.warning("GROQ_API_KEY not found, Groq calls will fail")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    async def call_openai(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Call OpenAI API (GPT-4o, GPT-4o-mini)
        
        Args:
            model: Model name (gpt-4o, gpt-4o-mini)
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with content, token counts, cost, latency
        """
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY")
        
        import time
        start_time = time.time()
        
        response = await self.openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = calculate_cost(
            model,
            input_tokens,
            output_tokens,
            self.COST_PER_1M
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            provider="openai"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    async def call_anthropic(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Call Anthropic API (Claude Haiku)
        
        Args:
            model: Model name (claude-haiku-3-5-sonnet-20241022)
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with content, token counts, cost, latency
        """
        if not self.anthropic_client:
            raise ValueError("Anthropic client not initialized. Check ANTHROPIC_API_KEY")
        
        import time
        start_time = time.time()
        
        # Anthropic uses different message format
        # Convert OpenAI format to Anthropic format
        system_message = ""
        claude_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        response = await self.anthropic_client.messages.create(
            model=model,
            system=system_message,
            messages=claude_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = calculate_cost(
            model,
            input_tokens,
            output_tokens,
            self.COST_PER_1M
        )
        
        return LLMResponse(
            content=response.content[0].text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            provider="anthropic"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    async def call_google(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Call Google Generative AI API (Gemini Flash)
        
        Args:
            model: Model name (gemini-1.5-flash)
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with content, token counts, cost, latency
        """
        if not self.google_client:
            raise ValueError("Google client not initialized. Check GOOGLE_API_KEY")

        import time
        start_time = time.time()

        # Convert OpenAI format to Gemini format
        gemini_messages = []
        system_instruction = ""

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                gemini_messages.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}],
                })

        response = await self.google_client.aio.models.generate_content(
            model=model,
            contents=gemini_messages,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction or None,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Gemini doesn't provide exact token counts, estimate
        input_tokens = sum(
            len(msg.get("parts", [{}])[0].get("text", "")) // 4
            for msg in gemini_messages
        )
        output_tokens = len(response.text) // 4
        cost = calculate_cost(model, input_tokens, output_tokens, self.COST_PER_1M)

        return LLMResponse(
            content=response.text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            provider="google",
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    async def call_ollama(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Call Ollama API (Llama-3 local)
        
        Args:
            model: Model name (llama-3)
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with content, token counts, cost (0), latency
        """
        if not self.ollama_client:
            raise ValueError("Ollama client not initialized. Check OLLAMA_BASE_URL")
        
        import time
        start_time = time.time()
        
        response = await self.ollama_client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Ollama provides token counts in response
        input_tokens = response.get("prompt_eval_count", 0)
        output_tokens = response.get("eval_count", 0)
        
        return LLMResponse(
            content=response["message"]["content"],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,  # Local models are free
            latency_ms=latency_ms,
            provider="ollama"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    async def call_groq(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Call Groq API (llama-3.1-8b-instant — free tier, ~500 tok/s)

        Groq uses an OpenAI-compatible chat completions API.
        """
        if not self.groq_client:
            raise ValueError("Groq client not initialized. Check GROQ_API_KEY")

        import time
        start_time = time.time()

        response = await self.groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = calculate_cost(model, input_tokens, output_tokens, self.COST_PER_1M)

        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            provider="groq",
        )

    async def call_llm(
        self,
        provider: str,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse:
        """
        Route to appropriate LLM provider

        Args:
            provider: Provider name (openai, anthropic, google, ollama, groq)
            model: Model name
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse from the appropriate provider
        """
        provider_map = {
            "openai": self.call_openai,
            "anthropic": self.call_anthropic,
            "google": self.call_google,
            "ollama": self.call_ollama,
            "groq": self.call_groq,
        }
        
        if provider not in provider_map:
            raise ValueError(f"Unknown provider: {provider}")
        
        return await provider_map[provider](
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


# Global client instance
llm_client = LLMClient()