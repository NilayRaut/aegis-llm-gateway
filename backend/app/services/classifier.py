"""
Complexity Classifier - Scores prompt complexity and routes to appropriate model
Uses embeddings + heuristics to determine complexity (0.0 to 1.0)
"""

import re
from typing import Tuple, Dict
import logging
import numpy as np

from app.services.embedder import get_embedder

logger = logging.getLogger(__name__)


class ComplexityClassifier:
    """
    Classifies prompt complexity and routes to appropriate model
    
    Complexity scoring combines:
    - Embedding-based semantic complexity
    - Text length and structure
    - Question type (factual vs analytical)
    - Domain keywords (technical, legal, medical)
    """
    
    # Routing thresholds: (min_score, max_score) -> model
    ROUTING_TABLE = {
        (0.0, 0.2): ("llama3.1", "ollama"),
        (0.2, 0.4): ("gemini-1.5-flash", "google"),
        (0.4, 0.6): ("gpt-4o-mini", "openai"),
        (0.6, 0.8): ("claude-haiku-3-5-sonnet-20241022", "anthropic"),
        (0.8, 1.0): ("gpt-4o", "openai"),
    }
    
    # Domain keywords that increase complexity
    DOMAIN_KEYWORDS = {
        'legal': [
            'contract', 'lawsuit', 'liability', 'jurisdiction', 'statute',
            'regulation', 'compliance', 'litigation', 'plaintiff', 'defendant'
        ],
        'medical': [
            'diagnosis', 'treatment', 'symptom', 'pathology', 'medication',
            'clinical', 'therapy', 'disease', 'patient', 'prognosis'
        ],
        'financial': [
            'investment', 'portfolio', 'derivative', 'hedge', 'arbitrage',
            'fiscal', 'monetary', 'inflation', 'recession', 'valuation'
        ],
        'technical': [
            'algorithm', 'implementation', 'architecture', 'optimization',
            'debug', 'refactor', 'scalability', 'latency', 'throughput'
        ]
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
        
        # 1. Semantic complexity (embedding-based)
        semantic_score = self._semantic_complexity(prompt)
        score += semantic_score * 0.3
        
        # 2. Text length and structure
        structure_score = self._structure_complexity(prompt)
        score += structure_score * 0.25
        
        # 3. Question type
        question_score = self._question_complexity(prompt)
        score += question_score * 0.25
        
        # 4. Domain complexity
        domain_score = self._domain_complexity(prompt)
        score += domain_score * 0.2
        
        # Normalize to 0.0-1.0
        score = min(max(score, 0.0), 1.0)
        
        logger.info(f"Prompt complexity score: {score:.3f}")
        return score
    
    def _semantic_complexity(self, prompt: str) -> float:
        """
        Estimate complexity based on semantic embedding
        Longer prompts with more diverse vocabulary have higher complexity
        """
        try:
            # Generate embedding
            embedding = get_embedder().encode(prompt)
            
            # Use embedding norm as a proxy for complexity
            # (more information = higher norm)
            norm = np.linalg.norm(embedding)
            
            # Normalize to 0.0-1.0 based on typical values
            return min(norm / 30.0, 1.0)
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return 0.0
    
    def _structure_complexity(self, prompt: str) -> float:
        """
        Estimate complexity based on text structure
        Longer, more structured prompts are more complex
        """
        score = 0.0
        
        # Word count (normalize around 50 words)
        word_count = len(prompt.split())
        score += min(word_count / 100, 1.0) * 0.4
        
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
        Estimate complexity based on question type
        Analytical questions are more complex than factual ones
        """
        score = 0.0
        
        # Simple factual questions
        factual_patterns = [
            r'\b(what|who|when|where|which)\b',
            r'\b(calculate|compute|count)\b',
        ]
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in factual_patterns):
            score += 0.2
        
        # Analytical questions
        analytical_patterns = [
            r'\b(why|how|explain|analyze|evaluate|compare)\b',
            r'\b(relationship|difference|impact|effect)\b',
        ]
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in analytical_patterns):
            score += 0.5
        
        # Complex reasoning
        complex_patterns = [
            r'\b(optimize|design|architect|implement)\b',
            r'\b(trade-off|constraint|requirement)\b',
        ]
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in complex_patterns):
            score += 0.8
        
        return min(score, 1.0)
    
    def _domain_complexity(self, prompt: str) -> float:
        """
        Estimate complexity based on domain-specific vocabulary
        Technical/legal/medical prompts are more complex
        """
        score = 0.0
        prompt_lower = prompt.lower()
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            keyword_count = sum(1 for kw in keywords if kw in prompt_lower)
            if keyword_count > 0:
                # More keywords = higher complexity
                score += min(keyword_count * 0.15, 0.5)
        
        return min(score, 1.0)
    
    def route(self, complexity_score: float) -> Tuple[str, str]:
        """
        Route to appropriate model based on complexity score
        
        Args:
            complexity_score: Score from 0.0 to 1.0
            
        Returns:
            Tuple of (model_name, provider_name)
        """
        for (min_score, max_score), (model, provider) in self.ROUTING_TABLE.items():
            if min_score <= complexity_score < max_score:
                logger.info(f"Routing to {model} (complexity: {complexity_score:.3f})")
                return model, provider
        
        # Default to highest tier
        return "gpt-4o", "openai"
    
    def classify_and_route(self, prompt: str) -> Dict:
        """
        Complete classification and routing in one call
        
        Args:
            prompt: The user's prompt text
            
        Returns:
            Dictionary with score, model, provider, and reasoning
        """
        score = self.score(prompt)
        model, provider = self.route(score)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(score, model)
        
        return {
            "complexity_score": score,
            "model": model,
            "provider": provider,
            "reasoning": reasoning,
            "confidence": 0.8  # Fixed confidence for now
        }
    
    def _generate_reasoning(self, score: float, model: str) -> str:
        """Generate human-readable reasoning for routing decision"""
        if score < 0.2:
            return f"Simple query routed to {model} for cost efficiency"
        elif score < 0.4:
            return f"Moderate query routed to {model} for balanced cost/quality"
        elif score < 0.6:
            return f"Standard query routed to {model} for good quality"
        elif score < 0.8:
            return f"Complex query routed to {model} for high quality"
        else:
            return f"Very complex query routed to {model} for best quality"


# Global classifier instance
classifier = ComplexityClassifier()