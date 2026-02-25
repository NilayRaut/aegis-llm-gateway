"""
API routes for Aegis backend
"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import PromptRequest, LLMResponse, DashboardStats, RoutingDecision
import uuid
import time

router = APIRouter()


@router.post("/chat", response_model=LLMResponse)
async def chat(request: PromptRequest):
    """
    Process a chat request with intelligent routing.
    
    - Classifies prompt complexity
    - Routes to appropriate model (Llama-3, GPT-4o-mini, GPT-4o)
    - Returns response with routing and cost info
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # TODO: Implement actual routing logic in Phase 3
    # For now, return a mock response for testing
    
    # Mock routing decision
    routing_decision = RoutingDecision(
        model="gpt-4o-mini",
        reason="Mock routing - Phase 1 scaffold",
        confidence=0.8,
        cache_hit=False
    )
    
    # Mock response
    latency_ms = int((time.time() - start_time) * 1000)
    
    return LLMResponse(
        response=f"Mock response to: {request.prompt[:50]}... (Phase 1 scaffold - implement routing in Phase 3)",
        model_used=routing_decision.model,
        cost=0.001,
        latency_ms=latency_ms,
        routing_decision=routing_decision,
        causal_analysis=None,
        request_id=request_id
    )


@router.get("/stats", response_model=DashboardStats)
async def get_stats():
    """
    Get dashboard statistics.
    
    Returns:
    - Total requests processed
    - Cache hit rate
    - Cost savings vs GPT-4o-only
    - Average latency
    - Hallucinations caught
    - Model distribution
    """
    # TODO: Implement actual stats from database in Phase 4
    
    return DashboardStats(
        total_requests=0,
        cache_hit_rate=0.0,
        cost_savings=0.0,
        avg_latency_ms=0,
        hallucinations_caught=0,
        model_distribution={"llama-3": 0, "gpt-4o-mini": 0, "gpt-4o": 0}
    )