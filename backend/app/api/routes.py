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
import logging

from fastapi import APIRouter, HTTPException

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
    "gemini-1.5-flash": 0,
    "gpt-4o-mini": 0,
    "claude-3-5-haiku-20241022": 0,
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
        security_result = security_checker.check(request.prompt)

        if security_result.blocked:
            logger.warning("Request %s blocked: %s", request_id, security_result.reason)
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


@router.get("/history")
async def history(limit: int = 50):
    """Return recent request history for the frontend dashboard."""
    return await db.get_recent_requests(limit=min(limit, 100))


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
