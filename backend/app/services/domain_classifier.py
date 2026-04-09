"""
Domain Classifier — keyword-based prompt domain detection.
Used by the security layer to enforce hard routing overrides for high-stakes domains.
"""

from dataclasses import dataclass


@dataclass
class DomainResult:
    domain: str            # "general" | "legal" | "medical" | "financial"
    forced_model: str | None  # "gpt-4o" for high-stakes domains, None otherwise


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
    Classify the domain of a prompt using keyword matching.

    Checks legal → medical → financial in order. Legal takes precedence
    because legal/medical are the highest-risk domains for hallucinations.
    "tax" is in financial but not legal — "liability" is checked under legal first.

    Returns:
        DomainResult with domain name and forced_model (gpt-4o for high-stakes, None otherwise)
    """
    p = prompt.lower()

    if any(k in p for k in _LEGAL):
        return DomainResult(domain="legal", forced_model="gpt-4o")

    if any(k in p for k in _MEDICAL):
        return DomainResult(domain="medical", forced_model="gpt-4o")

    if any(k in p for k in _FINANCIAL):
        return DomainResult(domain="financial", forced_model="gpt-4o")

    return DomainResult(domain="general", forced_model=None)
