"""
Startup provider connectivity check.

Runs once at startup as a fire-and-forget asyncio task. Pings each
provider with a single short request (max_tokens=3, temp=0, 5-second
timeout). Results are cached in _RESULTS and exposed via GET /api/provider-test.

No retries — one attempt per provider. If it fails, it's reported as
failed. This makes the status meaningful: "ok" means the key works now.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_TIMEOUT_S = 15
_RESULTS: dict[str, dict] = {}
_ALL_PROVIDERS = ["openai", "anthropic", "google", "groq", "ollama"]

_PING_MSG = [{"role": "user", "content": "Reply with one word: ok"}]


def _classify_error(e: Exception) -> str:
    """Map an exception to a status string."""
    name = type(e).__name__
    msg = str(e).lower()
    if "authentication" in name.lower() or "unauthorized" in msg or "api key" in msg or "invalid_api_key" in msg:
        return "auth_error"
    return "unavailable"


async def _ping_openai(client) -> tuple[str, int]:
    if not client.openai_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=_PING_MSG,
                temperature=0,
                max_tokens=3,
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        return "unavailable", 0
    except Exception as e:
        return _classify_error(e), 0


async def _ping_anthropic(client) -> tuple[str, int]:
    if not client.anthropic_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                messages=_PING_MSG,
                max_tokens=3,
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        return "unavailable", 0
    except Exception as e:
        return _classify_error(e), 0


async def _ping_google(client) -> tuple[str, int]:
    if not client.google_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.google_client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents="ok?",
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        return "unavailable", 0
    except Exception as e:
        return _classify_error(e), 0


async def _ping_groq(client) -> tuple[str, int]:
    if not client.groq_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=_PING_MSG,
                temperature=0,
                max_tokens=3,
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        return "unavailable", 0
    except Exception as e:
        return _classify_error(e), 0


async def _ping_ollama(client) -> tuple[str, int]:
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.ollama_client.chat(
                model="llama3.1",
                messages=_PING_MSG,
                options={"num_predict": 3},
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        return "unavailable", 0
    except Exception as e:
        return _classify_error(e), 0


async def check_all_providers(client) -> None:
    """
    Ping all providers concurrently. Store results in _RESULTS.
    Called as asyncio.create_task() at startup — does not block server boot.
    """
    global _RESULTS
    # Mark all as pending before checks begin (so /api/provider-test returns
    # something meaningful if fetched before checks complete)
    _RESULTS = {p: {"status": "pending", "latency_ms": 0} for p in _ALL_PROVIDERS}

    pings = [
        ("openai",    _ping_openai(client)),
        ("anthropic", _ping_anthropic(client)),
        ("google",    _ping_google(client)),
        ("groq",      _ping_groq(client)),
        ("ollama",    _ping_ollama(client)),
    ]

    results = await asyncio.gather(*[coro for _, coro in pings], return_exceptions=True)

    for (provider, _), result in zip(pings, results):
        if isinstance(result, Exception):
            status, latency = "unavailable", 0
        else:
            status, latency = result
        _RESULTS[provider] = {"status": status, "latency_ms": latency}
        logger.info("Provider check — %s: %s (%dms)", provider, status, latency)


def get_results() -> dict:
    """Return cached provider check results. Returns pending state if not run yet."""
    if not _RESULTS:
        return {p: {"status": "pending", "latency_ms": 0} for p in _ALL_PROVIDERS}
    return dict(_RESULTS)
