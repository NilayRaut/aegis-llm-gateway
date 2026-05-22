"""
API routes for Aegis backend.

Full pipeline per request:
  1. Security check     → block PII / injection / domain gate
  2. Cache lookup       → return cached response if similarity ≥ 0.85
  3. LLM routing        → classify complexity, route to cheapest capable model
  3.5 Hallucination     → Tier 1 hedging scan (all) + Tier 3 paraphrase variance (high-risk)
  4. Cache store        → save response for future cache hits
  5. DB logging         → persist cost, latency, domain, risk_level for dashboard
"""

import uuid
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    PromptRequest,
    LLMResponse,
    CausalAnalysis,
    DashboardStats,
    RoutingDecision,
)
from app.agents.router import router_agent
from app.services.security import security_checker
from app.services.cache import semantic_cache
from app.services.hallucination_detector import hallucination_detector
from app.services.llm_client import llm_client
from app import db

logger = logging.getLogger(__name__)
router = APIRouter()

# Default model keys always returned in model_distribution
# (so the frontend never needs to handle missing keys)
_DEFAULT_MODEL_DIST = {
    "llama3.1": 0,
    "gemini-2.5-flash": 0,
    "gpt-4o-mini": 0,
    "claude-haiku-4-5-20251001": 0,
    "gpt-4o": 0,
}


_RISK_ORDER = {"SAFE": 0, "MEDIUM": 1, "HIGH": 2}
_RISK_BY_ORDER = {v: k for k, v in _RISK_ORDER.items()}


def _risk_from_domain(domain: str) -> str:
    """Map domain to baseline risk level for DB logging."""
    if domain in ("legal", "medical"):
        return "HIGH"
    if domain == "financial":
        return "MEDIUM"
    return "SAFE"


def _merge_risk(domain_risk: str, detection_is_hallucination: bool, pathway: str | None) -> str:
    """
    Combine domain-based risk with hallucination detection result.
    Takes the higher of the two. Paraphrase variance → HIGH, hedging only → MEDIUM.
    """
    if not detection_is_hallucination:
        return domain_risk
    detection_risk = "HIGH" if pathway == "paraphrase_variance" else "MEDIUM"
    higher = max(_RISK_ORDER[domain_risk], _RISK_ORDER[detection_risk])
    return _RISK_BY_ORDER[higher]


@router.post("/chat", response_model=LLMResponse)
async def chat(request: PromptRequest):
    """
    Process a chat request through the full Aegis pipeline:
    Security → Cache → Route → Store → Log → Return
    """
    request_id = str(uuid.uuid4())

    try:
        # ── Step 1: Security check ────────────────────────────────────────────
        security_result = await security_checker.check_async(request.prompt)

        if security_result.blocked:
            logger.warning("Request %s blocked: %s", request_id, security_result.reason)
            await db.log_request(
                id=request_id,
                model_used="blocked",
                provider="",
                cost_usd=0.0,
                latency_ms=0,
                complexity_score=0.0,
                domain=security_result.domain or "general",
                cache_hit=False,
                risk_level="HIGH",
                security_blocked=True,
                security_reason=security_result.reason or "Security policy violation",
            )
            raise HTTPException(status_code=400, detail=security_result.reason)

        domain = security_result.domain
        risk_level = _risk_from_domain(domain)

        # ── Step 2: Semantic cache lookup ─────────────────────────────────────
        cached = semantic_cache.lookup(request.prompt)
        if cached is not None:
            logger.info("Cache HIT for request %s", request_id)

            await db.log_request(
                id=request_id,
                model_used=cached.get("model_used", "cache"),
                provider=cached.get("provider", ""),
                cost_usd=0.0,
                latency_ms=5,
                complexity_score=cached.get("complexity_score", 0.0),
                domain=domain,
                cache_hit=True,
                risk_level=risk_level,
                security_blocked=False,
            )

            routing = RoutingDecision(
                model=cached["routing_decision"]["model"],
                reason="Served from semantic cache (similarity ≥ 0.85)",
                confidence=cached["routing_decision"]["confidence"],
                cache_hit=True,
            )
            return LLMResponse(
                response=cached["response"],
                model_used=cached["model_used"],
                cost=0.0,
                latency_ms=5,
                routing_decision=routing,
                causal_analysis=None,
                request_id=request_id,
                complexity_score=cached.get("complexity_score", 0.0),
                domain=domain,
                risk_level=risk_level,
                provider=cached.get("provider", ""),
            )

        # ── Step 3: Route through LangGraph agent ─────────────────────────────
        result = await router_agent.process(
            prompt=request.prompt,
            context=request.context,
            forced_model=security_result.forced_model,
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # ── Step 3.5: Hallucination detection ─────────────────────────────────
        detection = await hallucination_detector.analyze(
            prompt=request.prompt,
            response=result["response"],
            model=result["model_used"],
            provider=result.get("provider", "openai"),
            complexity_score=result.get("complexity_score", 0.0),
            domain=domain,
            llm_client=llm_client,
        )
        risk_level = _merge_risk(risk_level, detection.is_hallucination, detection.pathway)

        # ── Step 4: Store in cache for future hits ────────────────────────────
        # Don't cache flagged responses — avoids perpetuating bad answers
        if not detection.is_hallucination:
            semantic_cache.add(request.prompt, result)

        # ── Step 5: Log to DB ─────────────────────────────────────────────────
        await db.log_request(
            id=request_id,
            model_used=result["model_used"],
            provider=result.get("provider", ""),
            cost_usd=result["cost"],
            latency_ms=result["latency_ms"],
            complexity_score=result.get("complexity_score", 0.0),
            domain=domain,
            cache_hit=False,
            risk_level=risk_level,
            security_blocked=False,
        )

        # ── Build and return response ──────────────────────────────────────────
        routing_decision = RoutingDecision(
            model=result["routing_decision"]["model"],
            reason=result["routing_decision"]["reason"],
            confidence=result["routing_decision"]["confidence"],
            cache_hit=False,
        )
        causal_analysis = CausalAnalysis(
            confidence=detection.confidence,
            pathway=detection.pathway,
            is_hallucination=detection.is_hallucination,
            explanation=detection.explanation,
            variance_score=detection.variance_score,
        )

        return LLMResponse(
            response=result["response"],
            model_used=result["model_used"],
            cost=result["cost"],
            latency_ms=result["latency_ms"],
            routing_decision=routing_decision,
            causal_analysis=causal_analysis,
            request_id=request_id,
            complexity_score=result.get("complexity_score", 0.0),
            domain=domain,
            risk_level=risk_level,
            provider=result.get("provider", ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error processing request %s", request_id)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(request: PromptRequest):
    """
    Streaming version of /chat — emits SSE events for each pipeline stage.
    Event types: status | done | error
    """
    async def _generate():
        request_id = str(uuid.uuid4())

        def _evt(type: str, **kwargs) -> str:
            return f"data: {json.dumps({'type': type, **kwargs})}\n\n"

        try:
            # Stage 1 — Security gate
            yield _evt("status", stage=1, label="Security Gate", message="Scanning for PII and injection patterns…")
            security_result = await security_checker.check_async(request.prompt)

            if security_result.blocked:
                await db.log_request(
                    id=request_id, model_used="blocked", provider="",
                    cost_usd=0.0, latency_ms=0, complexity_score=0.0,
                    domain=security_result.domain or "general", cache_hit=False,
                    risk_level="HIGH", security_blocked=True,
                    security_reason=security_result.reason or "Security policy violation",
                )
                yield _evt("status", stage=1, label="Security Gate", message=security_result.reason, done=True)
                yield _evt("error", message=security_result.reason, stage="security")
                return

            domain = security_result.domain
            risk_level = _risk_from_domain(domain)
            yield _evt("status", stage=1, label="Security Gate", message="Cleared", done=True)

            # Stage 2 — Semantic cache
            yield _evt("status", stage=2, label="Semantic Cache", message="Searching embedding cache (cosine ≥ 0.85)…")
            cached = semantic_cache.lookup(request.prompt)
            if cached is not None:
                await db.log_request(
                    id=request_id, model_used=cached.get("model_used", "cache"),
                    provider=cached.get("provider", ""), cost_usd=0.0, latency_ms=5,
                    complexity_score=cached.get("complexity_score", 0.0), domain=domain,
                    cache_hit=True, risk_level=risk_level, security_blocked=False,
                )
                yield _evt("status", stage=2, label="Semantic Cache", message="HIT — returning cached response", done=True)
                routing = RoutingDecision(
                    model=cached["routing_decision"]["model"],
                    reason="Served from semantic cache (similarity ≥ 0.85)",
                    confidence=cached["routing_decision"]["confidence"],
                    cache_hit=True,
                )
                from app.models.schemas import LLMResponse as LLMResponseSchema
                payload = LLMResponseSchema(
                    response=cached["response"], model_used=cached["model_used"],
                    cost=0.0, latency_ms=5, routing_decision=routing, causal_analysis=None,
                    request_id=request_id, complexity_score=cached.get("complexity_score", 0.0),
                    domain=domain, risk_level=risk_level, provider=cached.get("provider", ""),
                )
                yield _evt("done", data=payload.model_dump())
                return

            yield _evt("status", stage=2, label="Semantic Cache", message="Miss — no similar query found", done=True)

            # Stage 3 — Complexity scoring
            forced = security_result.forced_model
            if forced:
                yield _evt("status", stage=3, label="Complexity Classifier",
                           message=f"Domain gate active — bypassing classifier")
            else:
                yield _evt("status", stage=3, label="Complexity Classifier",
                           message="Scoring prompt across 4 factors…")

            # Router runs classify + route + LLM call internally
            result = await router_agent.process(
                prompt=request.prompt,
                context=request.context,
                forced_model=forced,
            )

            if result.get("error"):
                yield _evt("error", message=result["error"])
                return

            score_label = f"{result.get('complexity_score', 0):.2f}"
            model_label = result["model_used"]

            yield _evt("status", stage=3, label="Complexity Classifier",
                       message=f"Score {score_label}", done=True)

            # Stage 4 — Routing decision
            if forced:
                yield _evt("status", stage=4, label="Domain Gate",
                           message=f"Hard-routed to {forced} (sensitive domain)", done=True)
            else:
                yield _evt("status", stage=4, label="Routing Decision",
                           message=f"Routed to {model_label}", done=True)

            # Stage 5 — LLM call result
            yield _evt("status", stage=5, label="LLM Call",
                       message=f"Response in {result['latency_ms']}ms", done=True)

            # Stage 6 — Hallucination check
            yield _evt("status", stage=6, label="Hallucination Check", message="Running paraphrase variance test…")
            detection = await hallucination_detector.analyze(
                prompt=request.prompt, response=result["response"],
                model=result["model_used"], provider=result.get("provider", "openai"),
                complexity_score=result.get("complexity_score", 0.0),
                domain=domain, llm_client=llm_client,
            )
            risk_level = _merge_risk(risk_level, detection.is_hallucination, detection.pathway)
            risk_msg = f"Risk: {risk_level}" + (" — HIGH variance flagged" if detection.is_hallucination else "")
            yield _evt("status", stage=6, label="Hallucination Check", message=risk_msg, done=True)

            # Stage 7 — Cache store + DB log
            yield _evt("status", stage=7, label="Audit Log", message="Logging cost, latency, risk to SQLite…")
            if not detection.is_hallucination:
                semantic_cache.add(request.prompt, result)
            await db.log_request(
                id=request_id, model_used=result["model_used"],
                provider=result.get("provider", ""), cost_usd=result["cost"],
                latency_ms=result["latency_ms"],
                complexity_score=result.get("complexity_score", 0.0),
                domain=domain, cache_hit=False, risk_level=risk_level, security_blocked=False,
            )
            yield _evt("status", stage=7, label="Audit Log", message="Logged", done=True)

            # Done — emit full response
            routing_decision = RoutingDecision(
                model=result["routing_decision"]["model"],
                reason=result["routing_decision"]["reason"],
                confidence=result["routing_decision"]["confidence"],
                cache_hit=False,
            )
            causal_analysis = CausalAnalysis(
                confidence=detection.confidence, pathway=detection.pathway,
                is_hallucination=detection.is_hallucination, explanation=detection.explanation,
            )
            from app.models.schemas import LLMResponse as LLMResponseSchema
            payload = LLMResponseSchema(
                response=result["response"], model_used=result["model_used"],
                cost=result["cost"], latency_ms=result["latency_ms"],
                routing_decision=routing_decision, causal_analysis=causal_analysis,
                request_id=request_id, complexity_score=result.get("complexity_score", 0.0),
                domain=domain, risk_level=risk_level, provider=result.get("provider", ""),
            )
            yield _evt("done", data=payload.model_dump())

        except Exception as e:
            logger.exception("Streaming error for request %s", request_id)
            yield _evt("error", message=f"Internal error: {str(e)}")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
async def history(limit: int = 50):
    """Return recent request history for the frontend dashboard."""
    return await db.get_recent_requests(limit=min(limit, 100))


@router.get("/security/events")
async def security_events(limit: int = 20):
    """Return recent security-blocked requests for the security event log."""
    return await db.get_security_events(limit=min(limit, 50))


@router.get("/provider-health")
async def get_provider_health():
    """
    Live provider health board — per-provider query counts, average latency,
    and last-seen timestamp.  All five providers are always returned;
    those with no recorded requests show status 'unconfigured'.
    """
    rows = await db.get_provider_stats()
    recorded = {r["provider"]: r for r in rows}

    # All providers Aegis can route to
    all_providers = ["openai", "anthropic", "google", "groq", "ollama"]
    result = []
    for provider in all_providers:
        if provider in recorded:
            r = recorded[provider]
            result.append({
                "provider": provider,
                "status": "active",
                "total_queries": r["total_queries"],
                "avg_latency_ms": round(r["avg_latency_ms"]),
                "last_seen": r["last_seen"],
            })
        else:
            result.append({
                "provider": provider,
                "status": "unconfigured",
                "total_queries": 0,
                "avg_latency_ms": 0,
                "last_seen": None,
            })
    return result


@router.get("/provider-test")
async def get_provider_test():
    """
    Returns startup connectivity check results for each provider.
    Status values: ok | not_configured | auth_error | unavailable | pending
    """
    from app.services.provider_checker import get_results
    return get_results()


@router.get("/stats", response_model=DashboardStats)
async def get_stats():
    """
    Return aggregated dashboard statistics from SQLite.
    Merges with default model keys so frontend always gets all 5 models.
    """
    stats = await db.get_stats()

    model_dist = dict(_DEFAULT_MODEL_DIST)
    model_dist.update(stats["model_distribution"])

    return DashboardStats(
        total_requests=stats["total_requests"],
        cache_hit_rate=stats["cache_hit_rate"],
        cost_savings=stats["cost_savings"],
        avg_latency_ms=stats["avg_latency_ms"],
        hallucinations_caught=stats["hallucinations_caught"],
        model_distribution=model_dist,
    )


@router.get("/tier3-overhead")
async def get_tier3_overhead():
    """
    Per-stage Tier 3 (paraphrase variance) latency overhead — p50/p95/p99 over
    the most recent runs (in-memory ring buffer, resets on server restart).
    Returns null fields when no Tier 3 runs have been recorded yet.
    """
    return hallucination_detector.get_tier3_overhead_stats()


_breakdown_cache: dict = {}


@router.get("/domain-cost-breakdown")
async def get_domain_cost_breakdown():
    """
    Descriptive subgroup breakdown of routing cost by domain class.

    Reports average per-request cost for sensitive-domain queries
    (legal/medical/financial) vs general queries, stratified by complexity
    tier. The delta is mechanically expected by design (sensitive domains are
    unconditionally routed to gpt-4o by the hard-gate) — this is descriptive
    telemetry, not a causal estimate.

    Results are cached for 60 seconds to avoid recomputing on every dashboard poll.
    """
    import time
    from app.services.causal_analysis import run_domain_cost_breakdown

    now = time.time()
    if _breakdown_cache.get("ts") and now - _breakdown_cache["ts"] < 60:
        return _breakdown_cache["result"]

    rows = await db.get_all_requests_for_analysis()
    result = await run_domain_cost_breakdown(rows)

    _breakdown_cache["ts"] = now
    _breakdown_cache["result"] = result
    return result
