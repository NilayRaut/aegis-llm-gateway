"""
API routes for Aegis backend
"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import PromptRequest, LLMResponse, DashboardStats, RoutingDecision
from app.agents.router import router_agent
import uuid
import time

router = APIRouter()


@router.post("/chat", response_model=LLMResponse)
async def chat(request: PromptRequest):
    """
    Process a chat request with intelligent routing.
    
    - Classifies prompt complexity
    - Routes to appropriate model (5-tier system)
    - Returns response with routing and cost info
    """
    request_id = str(uuid.uuid4())
    
    try:
        # Process request through router agent
        result = await router_agent.process(
            prompt=request.prompt,
            context=request.context
        )
        
        # Check for errors
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Build routing decision
        routing_decision = RoutingDecision(
            model=result["routing_decision"]["model"],
            reason=result["routing_decision"]["reason"],
            confidence=result["routing_decision"]["confidence"],
            cache_hit=result["routing_decision"]["cache_hit"]
        )
        
        # Return response
        return LLMResponse(
            response=result["response"],
            model_used=result["model_used"],
            cost=result["cost"],
            latency_ms=result["latency_ms"],
            routing_decision=routing_decision,
            causal_analysis=None,  # Not implemented in Phase 2
            request_id=request_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
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
        model_distribution={
            "llama-3": 0,
            "gemini-1.5-flash": 0,
            "gpt-4o-mini": 0,
            "claude-haiku-3-5-sonnet-20241022": 0,
            "gpt-4o": 0
        }
    )
