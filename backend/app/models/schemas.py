"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime


class PromptRequest(BaseModel):
    """Request schema for chat endpoint"""
    prompt: str = Field(..., min_length=1, max_length=4000, description="The user's prompt")
    context: Optional[str] = Field(None, max_length=10000, description="Optional context for the prompt")
    max_tokens: Optional[int] = Field(default=500, ge=50, le=4000, description="Max tokens in response")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="Response randomness")


class RoutingDecision(BaseModel):
    """Schema for routing decision"""
    model: Literal["llama-3", "gpt-4o-mini", "gpt-4o"] = Field(..., description="Which model was selected")
    reason: str = Field(..., description="Why this model was chosen")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in routing decision")
    cache_hit: bool = Field(default=False, description="Whether response came from cache")


class CausalAnalysis(BaseModel):
    """Schema for causal hallucination analysis"""
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in causal link")
    pathway: Optional[str] = Field(None, description="Identified causal pathway for hallucination")
    is_hallucination: bool = Field(..., description="Whether response is flagged as hallucination")
    explanation: str = Field(..., description="Human-readable explanation")


class LLMResponse(BaseModel):
    """Response schema for chat endpoint"""
    model_config = ConfigDict(protected_namespaces=())
    
    response: str = Field(..., description="The LLM's response")
    model_used: str = Field(..., description="Which model generated the response")
    cost: float = Field(..., ge=0.0, description="Cost of this request in USD")
    latency_ms: int = Field(..., ge=0, description="Response latency in milliseconds")
    
    routing_decision: RoutingDecision = Field(..., description="Routing decision details")
    causal_analysis: Optional[CausalAnalysis] = Field(None, description="Causal analysis results")
    
    request_id: str = Field(..., description="Unique request identifier")


class DashboardStats(BaseModel):
    """Schema for dashboard statistics"""
    model_config = ConfigDict(protected_namespaces=())
    
    total_requests: int = Field(..., ge=0, description="Total number of requests")
    cache_hit_rate: float = Field(..., ge=0.0, le=100.0, description="Cache hit rate percentage")
    cost_savings: float = Field(..., ge=0.0, description="Dollars saved vs GPT-4o-only routing")
    avg_latency_ms: int = Field(..., ge=0, description="Average response latency")
    hallucinations_caught: int = Field(..., ge=0, description="Number of hallucinations flagged")
    model_distribution: dict = Field(..., description="Distribution of requests across models")