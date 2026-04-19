"""
Domain Classifier — classifies prompt domain for security hard-routing.

Two paths:
- classify_domain()       Synchronous keyword fallback (always available)
- classify_domain_async() LLM-based via Groq llama — avoids false positives
                          from keyword matching ("patient" → medical,
                          "option" → financial). Falls back to keyword on failure.
"""

import asyncio
import logging
from dataclasses import dataclass

from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class DomainResult:
    domain: str               # "general" | "legal" | "medical" | "financial"
    forced_model: str | None  # "gpt-4o" for high-stakes domains, None otherwise


# ── LLM-based classifier prompt ────────────────────────────────────────────
_DOMAIN_PROMPT = """Classify this user prompt's domain. Reply with ONLY one word from this list:
legal, medical, financial, general

legal:     contracts, laws, regulations, lawsuits, compliance, GDPR, privacy law, legal rights, court cases
medical:   diagnosis, symptoms, dosage, treatment, drugs, clinical advice, patient conditions, medical procedures
financial: investments, stocks, taxes, portfolio, trading, financial planning, asset management, retirement funds
general:   anything else — coding, science, history, technology, math, opinion, creative writing, general knowledge

Answer ONLY the single word. If in doubt, answer general."""

# ── Keyword fallback lists (used when Groq is unavailable) ─────────────────
_LEGAL = [
    "contract", "lawsuit", "liability", "enforceable", "statute", "regulation",
    "attorney", "compliance", "jurisdiction", "copyright", "patent", "clause",
    "arbitration", "non-compete", "noncompete", "legal advice", "court",
    "gdpr", "privacy regulation", "data protection", "data breach",
    "data subject", "article 17", "right to erasure", "right to be forgotten",
    "dpa", "privacy law", "personal data",
]

_MEDICAL = [
    "diagnosis", "treatment", "dosage", "symptom", "prescription", "medication",
    "disease", "clinical", "patient", "therapy", "drug interaction", "side effect",
    "medical advice", "doctor", "hospital",
]

_FINANCIAL = [
    "investment", "portfolio", "derivative", "hedge", "securities", "equity",
    "asset", "dividend", "trading", "fund", "stock", "bond", "option",
    "financial advice", "tax advice",
]


def classify_domain(prompt: str) -> DomainResult:
    """
    Classify domain via keyword matching. Synchronous fallback.

    Checks legal → medical → financial in order. Legal takes precedence
    because legal/medical are the highest-risk domains for hallucinations.
    """
    p = prompt.lower()

    if any(k in p for k in _LEGAL):
        return DomainResult(domain="legal", forced_model="gpt-4o")

    if any(k in p for k in _MEDICAL):
        return DomainResult(domain="medical", forced_model="gpt-4o")

    if any(k in p for k in _FINANCIAL):
        return DomainResult(domain="financial", forced_model="gpt-4o")

    return DomainResult(domain="general", forced_model=None)


async def classify_domain_async(prompt: str) -> DomainResult:
    """
    LLM-based domain classification via Groq llama (free, ~100ms, 3s timeout).

    Eliminates false positives from keyword matching:
      - "I'm very patient" no longer triggers medical → GPT-4o
      - "this option looks good" no longer triggers financial → GPT-4o
      - "the contractor needs" no longer triggers legal → GPT-4o

    Falls back to keyword classify_domain() on any failure.
    """
    if not llm_client.groq_client:
        return classify_domain(prompt)
    try:
        response = await asyncio.wait_for(
            llm_client.call_groq(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": _DOMAIN_PROMPT},
                    {"role": "user", "content": f'Prompt: "{prompt}"'},
                ],
                temperature=0.0,
                max_tokens=5,
            ),
            timeout=3.0,
        )
        domain = response.content.strip().lower().split()[0]
        if domain not in ("legal", "medical", "financial", "general"):
            domain = "general"
        forced_model = "gpt-4o" if domain in ("legal", "medical", "financial") else None
        return DomainResult(domain=domain, forced_model=forced_model)
    except Exception as e:
        logger.warning("LLM domain classifier failed (%s), using keyword fallback", type(e).__name__)
        return classify_domain(prompt)
