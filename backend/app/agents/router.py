"""
LangGraph Router Agent - Stateful routing agent for LLM requests
Orchestrates: classify → route → call_llm → return
"""

from typing import TypedDict, Annotated, Optional
from operator import add
import logging
import os
import httpx
from langgraph.graph import StateGraph, END

from app.services.classifier import classifier
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)


class RouterState(TypedDict):
    """State for the routing agent"""
    prompt: str
    context: str | None
    forced_model: str | None  # set by security layer for high-stakes domains
    complexity_score: float
    model: str
    provider: str
    reasoning: str
    confidence: float
    response: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    error: str | None


class RouterAgent:
    """
    LangGraph-based routing agent for intelligent LLM request handling
    """
    
    def __init__(self):
        """Initialize the router agent"""
        self.graph = self._build_graph()
        self._ollama_reachable: Optional[bool] = None  # cached after first check
        logger.info("Router agent initialized with compiled graph")

    def _ollama_available(self) -> bool:
        """
        Check once whether a local Ollama server is reachable.
        Result is cached for the lifetime of the process.
        """
        if self._ollama_reachable is not None:
            return self._ollama_reachable
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            r = httpx.get(f"{ollama_url}/api/tags", timeout=1.0)
            self._ollama_reachable = r.status_code == 200
        except Exception:
            self._ollama_reachable = False
        logger.info("Ollama reachable: %s", self._ollama_reachable)
        return self._ollama_reachable
    
    def _build_graph(self) -> StateGraph:
        """
        Build the routing state graph
        
        Graph flow:
        classify → route → call_llm → return
        """
        workflow = StateGraph(RouterState)
        
        # Add nodes
        workflow.add_node("classify", self._classify_node)
        workflow.add_node("route", self._route_node)
        workflow.add_node("call_llm", self._call_llm_node)
        workflow.add_node("return", self._return_node)
        
        # Add edges
        workflow.set_entry_point("classify")
        workflow.add_edge("classify", "route")
        workflow.add_edge("route", "call_llm")
        workflow.add_edge("call_llm", "return")
        workflow.add_edge("return", END)
        
        return workflow.compile()
    
    async def _classify_node(self, state: RouterState) -> RouterState:
        """
        Classify prompt complexity
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with complexity score
        """
        logger.info("Running classify node")
        
        try:
            # Get full prompt (including context if provided)
            full_prompt = state["prompt"]
            if state.get("context"):
                full_prompt = f"Context: {state['context']}\n\nQuestion: {state['prompt']}"
            
            # Classify and route
            result = classifier.classify_and_route(full_prompt)
            
            state["complexity_score"] = result["complexity_score"]
            state["model"] = result["model"]
            state["provider"] = result["provider"]
            state["reasoning"] = result["reasoning"]
            state["confidence"] = result["confidence"]
            
            logger.info(f"Classification complete: {state['model']} (score: {state['complexity_score']:.3f})")
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            state["error"] = f"Classification failed: {str(e)}"
            # Fallback to default model
            state["model"] = "gpt-4o-mini"
            state["provider"] = "openai"
            state["reasoning"] = "Classification failed, using default model"
            state["confidence"] = 0.5
        
        return state
    
    async def _route_node(self, state: RouterState) -> RouterState:
        """
        Validate routing decision and apply domain-forced model override if set.

        If the security layer injected a forced_model (legal/medical/financial domains),
        override the classifier's choice here. This is the "deterministic wall the
        probabilistic system cannot breach."
        """
        if state.get("forced_model"):
            state["model"] = state["forced_model"]
            state["provider"] = "openai"
            state["reasoning"] = (
                f"Domain override: hard-routed to {state['forced_model']} "
                f"(high-stakes domain — classifier decision bypassed)"
            )
            logger.info(f"Route node: forced override → {state['forced_model']}")
        else:
            logger.info(f"Route node: {state['provider']} / {state['model']}")

        return state
    
    async def _call_llm_node(self, state: RouterState) -> RouterState:
        """
        Call the appropriate LLM
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with LLM response, tokens, cost, latency
        """
        logger.info(f"Calling LLM: {state['model']}")
        
        # Build messages once — reused for primary call and any fallback
        messages = []
        if state.get("context"):
            messages.append({
                "role": "system",
                "content": f"Use the following context to answer: {state['context']}"
            })
        messages.append({
            "role": "user",
            "content": state["prompt"]
        })

        try:
            # For the cheap tier (groq), prefer local Ollama when available
            if state["provider"] == "groq" and self._ollama_available():
                logger.info("Local Ollama reachable — using llama3.1 instead of Groq")
                response = await llm_client.call_ollama(
                    model="llama3.1",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500,
                )
                state["model"] = "llama3.1"
                state["provider"] = "ollama"
                state["reasoning"] = state["reasoning"].replace(
                    "llama-3.1-8b-instant", "llama3.1"
                ) + " (local Ollama)"
            else:
                response = await llm_client.call_llm(
                    provider=state["provider"],
                    model=state["model"],
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500,
                )
            state["response"] = response.content
            state["input_tokens"] = response.input_tokens
            state["output_tokens"] = response.output_tokens
            state["cost_usd"] = response.cost_usd
            state["latency_ms"] = response.latency_ms
            logger.info(f"LLM call complete: {response.latency_ms}ms, ${response.cost_usd:.6f}")

        except Exception as primary_err:
            logger.error(f"LLM call error: {primary_err}")

            # Fallback: if the primary provider isn't openai, try gpt-4o-mini
            if state["provider"] != "openai":
                logger.warning(
                    "Primary provider '%s' failed — falling back to gpt-4o-mini",
                    state["provider"],
                )
                try:
                    response = await llm_client.call_openai(
                        model="gpt-4o-mini",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=500,
                    )
                    state["model"] = "gpt-4o-mini"
                    state["provider"] = "openai"
                    state["reasoning"] += " (fallback: primary provider unavailable)"
                    state["response"] = response.content
                    state["input_tokens"] = response.input_tokens
                    state["output_tokens"] = response.output_tokens
                    state["cost_usd"] = response.cost_usd
                    state["latency_ms"] = response.latency_ms
                    logger.info("Fallback to gpt-4o-mini succeeded")
                    return state
                except Exception as fallback_err:
                    logger.error("Fallback also failed: %s", fallback_err)

            state["error"] = f"LLM call failed: {str(primary_err)}"
            state["response"] = "I apologize, but I encountered an error processing your request. Please try again."
            state["cost_usd"] = 0.0
            state["latency_ms"] = 0
        
        return state
    
    async def _return_node(self, state: RouterState) -> RouterState:
        """
        Final node - prepare for return
        
        Args:
            state: Current agent state
            
        Returns:
            Final state (no changes needed)
        """
        logger.info("Return node: agent execution complete")
        return state
    
    async def process(self, prompt: str, context: str = None, forced_model: str | None = None) -> dict:
        """
        Process a request through the routing agent
        
        Args:
            prompt: User's prompt
            context: Optional context for the prompt
            
        Returns:
            Dictionary with complete routing and response information
        """
        # Initialize state
        initial_state: RouterState = {
            "prompt": prompt,
            "context": context,
            "forced_model": forced_model,
            "complexity_score": 0.0,
            "model": "",
            "provider": "",
            "reasoning": "",
            "confidence": 0.0,
            "response": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": None,
        }
        
        try:
            # Run the graph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Build response
            return {
                "response": final_state["response"],
                "model_used": final_state["model"],
                "provider": final_state["provider"],
                "complexity_score": final_state["complexity_score"],
                "routing_decision": {
                    "model": final_state["model"],
                    "reason": final_state["reasoning"],
                    "confidence": final_state["confidence"],
                    "cache_hit": False,
                },
                "cost": final_state["cost_usd"],
                "latency_ms": final_state["latency_ms"],
                "input_tokens": final_state["input_tokens"],
                "output_tokens": final_state["output_tokens"],
                "error": final_state["error"],
            }
            
        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            return {
                "response": f"Agent error: {str(e)}",
                "model_used": "error",
                "provider": "",
                "complexity_score": 0.0,
                "routing_decision": {
                    "model": "error",
                    "reason": f"Agent failed: {str(e)}",
                    "confidence": 0.0,
                    "cache_hit": False,
                },
                "cost": 0.0,
                "latency_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            }


# Global router agent instance
router_agent = RouterAgent()