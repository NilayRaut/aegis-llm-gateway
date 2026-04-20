"""
Complexity Classifier - Scores prompt complexity and routes to appropriate model
Uses embeddings + heuristics to determine complexity (0.0 to 1.0)
"""

import asyncio
import random
import re
from typing import Tuple, Dict, List
import logging
import numpy as np

from app.services.embedder import get_embedder
from app.services.llm_client import llm_client

_CLASSIFIER_PROMPT = """Rate the complexity of this user prompt for LLM routing.
Return ONLY a decimal number 0.0–1.0. No explanation, no units, nothing else.

Scale:
0.00–0.20  Trivial: basic facts, simple lookups, yes/no (capitals, dates, unit conversions)
0.20–0.45  Simple: common how/why questions, brief explanations (Why does X? How does Y work?)
0.45–0.65  Moderate: nuanced reasoning, comparisons, conceptual depth required
0.65–0.80  Complex: technical design, expert knowledge, implementation details
0.80–1.00  Expert: multi-constraint architecture, research-level, system design at scale"""

logger = logging.getLogger(__name__)

# Prototype embeddings cached at module level — computed once on first classify() call
_PROTOTYPE_EMBEDDINGS: 'dict | None' = None


class ComplexityClassifier:
    """
    Classifies prompt complexity and routes to appropriate model
    
    Complexity scoring combines:
    - Embedding-based semantic complexity
    - Text length and structure
    - Question type (factual vs analytical)
    - Domain keywords (technical, legal, medical)
    """
    
    # Routing table: (upper_threshold, [(primary_model, primary_provider), ...alternates])
    # Primary is first in each pool — route() returns primary for determinism.
    # classify_and_route() uses random.choice(pool) for live provider rotation.
    # Bands are deliberately widened for Gemini and Claude so the common 0.20–0.65
    # score range spreads traffic across all three non-OpenAI providers.
    ROUTING_TABLE: List[Tuple[float, List[Tuple[str, str]]]] = [
        (0.20, [("llama-3.1-8b-instant", "groq")]),
        (0.45, [("gemini-2.0-flash", "google"), ("claude-3-5-haiku-20241022", "anthropic")]),
        (0.65, [("claude-3-5-haiku-20241022", "anthropic"), ("gemini-2.0-flash", "google")]),
        (0.80, [("gpt-4o-mini", "openai"), ("claude-3-5-haiku-20241022", "anthropic")]),
        (1.01, [("gpt-4o", "openai")]),
    ]
    
    # Domain prototype sentences for semantic similarity matching.
    # Each list represents the "centre" of that domain's semantic space.
    # Cosine similarity against these replaces brittle keyword lists.
    DOMAIN_PROTOTYPES = {
        'technical': [
            "software architecture, algorithms, data structures, system design",
            "programming, code implementation, API design, database schema",
            "distributed systems, microservices, event sourcing, CQRS, Kubernetes",
            "machine learning, neural networks, model training, optimization",
        ],
        'legal': [
            "laws, regulations, contracts, compliance, legal liability",
            "court cases, lawsuits, attorneys, jurisdiction, statute",
            "GDPR, data protection, privacy regulation, right to erasure",
        ],
        'medical': [
            "disease, diagnosis, treatment, medication, clinical symptoms",
            "patient health, medical procedure, therapy, prognosis",
        ],
        'financial': [
            "investment, portfolio, stocks, financial analysis, valuation",
            "fiscal policy, monetary economics, inflation, derivatives",
        ],
    }
    
    def __init__(self):
        """Initialize classifier — embedder loads lazily on first use."""
        pass
    
    def score(self, prompt: str) -> float:
        """
        Score prompt complexity from 0.0 (simple) to 1.0 (complex)
        
        Args:
            prompt: The user's prompt text
            
        Returns:
            Complexity score between 0.0 and 1.0
        """
        score = 0.0
        
        # 1. Semantic complexity (vocabulary richness: TTR + avg word length)
        semantic_score = self._semantic_complexity(prompt)
        score += semantic_score * 0.20

        # 2. Text length and structure
        structure_score = self._structure_complexity(prompt)
        score += structure_score * 0.20

        # 3. Question type — primary differentiator for short prompts
        question_score = self._question_complexity(prompt)
        score += question_score * 0.35

        # 4. Domain complexity
        domain_score = self._domain_complexity(prompt)
        score += domain_score * 0.25
        
        # Normalize to 0.0-1.0
        score = min(max(score, 0.0), 1.0)
        
        logger.info(f"Prompt complexity score: {score:.3f}")
        return score
    
    def _semantic_complexity(self, prompt: str) -> float:
        """
        Vocabulary richness as a proxy for semantic complexity.
        Combines type-token ratio (lexical diversity) and average word length
        (technical vocabulary density). No embedding model required.
        """
        words = re.findall(r'\b[a-zA-Z]+\b', prompt.lower())
        if not words:
            return 0.0
        # Type-token ratio: unique words / total words (0.0–1.0)
        ttr = len(set(words)) / len(words)
        # Average word length, normalized: 3-char avg → 0.0, 10-char avg → 1.0
        avg_len = sum(len(w) for w in words) / len(words)
        len_score = max(min((avg_len - 3.0) / 7.0, 1.0), 0.0)
        return ttr * 0.5 + len_score * 0.5
    
    def _structure_complexity(self, prompt: str) -> float:
        """
        Estimate complexity based on text structure
        Longer, more structured prompts are more complex
        """
        score = 0.0
        
        # Word count — piecewise so short prompts score low and long prompts score high
        words = prompt.split()
        word_count = len(words)
        if word_count < 10:
            word_score = word_count / 10.0 * 0.1
        elif word_count < 30:
            word_score = 0.1 + (word_count - 10) / 20.0 * 0.2
        elif word_count < 80:
            word_score = 0.3 + (word_count - 30) / 50.0 * 0.2
        else:
            word_score = min(0.5 + (word_count - 80) / 120.0 * 0.3, 0.8)
        score += word_score * 0.4
        
        # Sentence count
        sentences = re.split(r'[.!?]+', prompt)
        sentence_count = len([s for s in sentences if s.strip()])
        score += min(sentence_count / 10, 1.0) * 0.3
        
        # Presence of lists/bullets
        if re.search(r'[-•*]\s+', prompt):
            score += 0.15
        
        # Presence of numbered points
        if re.search(r'\d+\.', prompt):
            score += 0.15
        
        return min(score, 1.0)
    
    def _question_complexity(self, prompt: str) -> float:
        """
        Estimate complexity based on question type.
        Tiers are mutually exclusive — the highest matching tier wins.
        """
        # Complex reasoning and implementation/creation tasks (highest tier)
        complex_patterns = [
            r'\b(optimize|design|architect|implement|write|code|create|build|derive|prove|debug|refactor)\b',
            r'\b(trade-off|constraint|requirement)\b',
        ]
        if any(re.search(p, prompt, re.IGNORECASE) for p in complex_patterns):
            return 0.8

        # Analytical questions (middle tier)
        analytical_patterns = [
            r'\b(why|how|explain|analyze|evaluate|compare)\b',
            r'\b(relationship|difference|impact|effect)\b',
        ]
        if any(re.search(p, prompt, re.IGNORECASE) for p in analytical_patterns):
            return 0.5

        # Simple factual questions (lowest tier)
        factual_patterns = [
            r'\b(what|who|when|where|which)\b',
            r'\b(calculate|compute|count)\b',
        ]
        if any(re.search(p, prompt, re.IGNORECASE) for p in factual_patterns):
            return 0.2

        # No match — open-ended prompt, mid-low complexity
        return 0.3
    
    def _domain_complexity(self, prompt: str) -> float:
        """
        Estimate domain complexity via cosine similarity to prototype sentences.
        fastembed returns L2-normalized vectors, so similarity = dot product.
        Returns the maximum similarity across all domains (0.0–1.0).
        """
        global _PROTOTYPE_EMBEDDINGS
        try:
            embedder = get_embedder()
            if _PROTOTYPE_EMBEDDINGS is None:
                _PROTOTYPE_EMBEDDINGS = {
                    domain: embedder.encode(sentences)
                    for domain, sentences in self.DOMAIN_PROTOTYPES.items()
                }
            prompt_emb = embedder.encode(prompt)   # shape (384,)
            max_sim = 0.0
            for protos in _PROTOTYPE_EMBEDDINGS.values():
                sims = protos @ prompt_emb          # (N,) cosine similarities
                domain_max = float(np.max(sims))
                if domain_max > max_sim:
                    max_sim = domain_max
            return max_sim
        except Exception as e:
            logger.warning(f"Domain embedding similarity failed: {e}")
            return 0.0
    
    def route(self, complexity_score: float) -> Tuple[str, str]:
        """
        Route to the primary model for a complexity score (deterministic).

        Returns the first (primary) entry in the matching band's pool.
        Tests and callers that need a stable result should use this method.
        classify_and_route() applies random.choice for live provider rotation.

        Args:
            complexity_score: Score from 0.0 to 1.0

        Returns:
            Tuple of (model_name, provider_name)
        """
        for threshold, pool in self.ROUTING_TABLE:
            if complexity_score < threshold:
                model, provider = pool[0]
                logger.info(f"Routing to {model} (complexity: {complexity_score:.3f})")
                return model, provider

        # Fallback — should not be reached with threshold 1.01 in table
        return "gpt-4o", "openai"
    
    def classify_and_route(self, prompt: str) -> Dict:
        """
        Complete classification and routing in one call, with provider rotation.

        Selects randomly from the matching band's provider pool so traffic
        distributes across all available providers — not just the primary.

        Args:
            prompt: The user's prompt text

        Returns:
            Dictionary with score, model, provider, and reasoning
        """
        score = self.score(prompt)

        # Find the matching band's pool and select randomly for rotation
        model, provider = self.route(score)  # default (primary)
        for threshold, pool in self.ROUTING_TABLE:
            if score < threshold:
                model, provider = random.choice(pool)
                break

        reasoning = self._generate_reasoning(score, model)

        return {
            "complexity_score": score,
            "model": model,
            "provider": provider,
            "reasoning": reasoning,
            "confidence": self._routing_confidence(score)
        }
    
    async def score_async(self, prompt: str) -> float:
        """
        LLM-based complexity scoring via Groq llama (free, ~100ms).
        Falls back to heuristic score() on any failure or unavailability.
        Capped at 3 seconds total (including any retry) to keep the request path fast.
        """
        if not llm_client.groq_client:
            return self.score(prompt)
        try:
            response = await asyncio.wait_for(
                llm_client.call_groq(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": _CLASSIFIER_PROMPT},
                        {"role": "user", "content": f'Prompt: "{prompt}"'},
                    ],
                    temperature=0.0,
                    max_tokens=5,
                ),
                timeout=3.0,
            )
            raw = response.content.strip().split()[0]
            return max(0.0, min(1.0, float(raw)))
        except Exception as e:
            logger.warning("LLM classifier failed (%s), using heuristic", type(e).__name__)
            return self.score(prompt)

    async def classify_and_route_async(self, prompt: str) -> Dict:
        """
        Async classification and routing using LLM-based scoring with provider rotation.
        Drop-in async replacement for classify_and_route() — same output format.
        """
        score = await self.score_async(prompt)

        model, provider = self.route(score)  # primary (deterministic default)
        for threshold, pool in self.ROUTING_TABLE:
            if score < threshold:
                model, provider = random.choice(pool)
                break

        return {
            "complexity_score": score,
            "model": model,
            "provider": provider,
            "reasoning": self._generate_reasoning(score, model),
            "confidence": self._routing_confidence(score),
        }

    def _routing_confidence(self, score: float) -> float:
        """
        Confidence that the score landed in the correct routing band.
        Scores near a tier boundary are less certain; scores deep in a band are more certain.
        Thresholds match ROUTING_TABLE upper bounds.
        """
        thresholds = [0.20, 0.45, 0.65, 0.80]
        min_dist = min(abs(score - t) for t in thresholds)
        return round(min(0.5 + min_dist * 3.0, 0.95), 2)

    def _generate_reasoning(self, score: float, model: str) -> str:
        """Generate human-readable reasoning for routing decision"""
        if score < 0.20:
            return f"Simple query routed to {model} for cost efficiency"
        elif score < 0.45:
            return f"Moderate query routed to {model} for balanced cost/quality"
        elif score < 0.65:
            return f"Standard query routed to {model} for good quality"
        elif score < 0.80:
            return f"Complex query routed to {model} for high quality"
        else:
            return f"Very complex query routed to {model} for best quality"


# Global classifier instance
classifier = ComplexityClassifier()