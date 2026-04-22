"""
Startup provider connectivity check.

Runs once at startup as a fire-and-forget asyncio task. Pings each
provider with a single short request (max_tokens=3, temp=0, 15-second
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


def _classify_error(e: BaseException, provider: str) -> str:
    """Map an exception to a status string, logging the raw error for diagnostics."""
    name = type(e).__name__
    msg = str(e).lower()
    logger.warning("Provider ping failed — %s: [%s] %s", provider, name, str(e)[:200])
    if "authentication" in name.lower() or "unauthorized" in msg or "api key" in msg or "invalid_api_key" in msg:
        return "auth_error"
    if "resource_exhausted" in msg or "quota" in msg or "credits are depleted" in msg or "429" in msg:
        return "quota_exceeded"
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
        logger.warning("Provider ping timed out — openai (%ds)", _TIMEOUT_S)
        return "unavailable", 0
    except BaseException as e:
        return _classify_error(e, "openai"), 0


async def _ping_anthropic(client) -> tuple[str, int]:
    if not client.anthropic_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                messages=_PING_MSG,
                max_tokens=3,
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        logger.warning("Provider ping timed out — anthropic (%ds)", _TIMEOUT_S)
        return "unavailable", 0
    except BaseException as e:
        return _classify_error(e, "anthropic"), 0


async def _ping_google(client) -> tuple[str, int]:
    if not client.google_client:
        return "not_configured", 0
    t0 = time.time()
    try:
        await asyncio.wait_for(
            client.google_client.aio.models.generate_content(
                model="gemini-2.5-flash-preview-04-17",
                contents="ok?",
            ),
            timeout=_TIMEOUT_S,
        )
        return "ok", int((time.time() - t0) * 1000)
    except asyncio.TimeoutError:
        logger.warning("Provider ping timed out — google (%ds)", _TIMEOUT_S)
        return "unavailable", 0
    except BaseException as e:
        return _classify_error(e, "google"), 0


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
        logger.warning("Provider ping timed out — groq (%ds)", _TIMEOUT_S)
        return "unavailable", 0
    except BaseException as e:
        return _classify_error(e, "groq"), 0


async def _ping_ollama(client) -> tuple[str, int]:
    if not client.ollama_client:
        return "not_configured", 0
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
        logger.warning("Provider ping timed out — ollama (%ds)", _TIMEOUT_S)
        return "unavailable", 0
    except BaseException as e:
        return _classify_error(e, "ollama"), 0


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
        if isinstance(result, BaseException):
            logger.warning(
                "Provider ping raised unhandled exception — %s: [%s] %s",
                provider, type(result).__name__, str(result)[:200],
            )
            status, latency = "unavailable", 0
        else:
            status, latency = result
        _RESULTS[provider] = {"status": status, "latency_ms": latency}
        if status in ("auth_error", "unavailable"):
            logger.warning("Provider check — %s: %s (%dms)", provider, status, latency)
        else:
            logger.info("Provider check — %s: %s (%dms)", provider, status, latency)


def get_results() -> dict:
    """Return cached provider check results. Returns pending state if not run yet."""
    if not _RESULTS:
        return {p: {"status": "pending", "latency_ms": 0} for p in _ALL_PROVIDERS}
    return dict(_RESULTS)
