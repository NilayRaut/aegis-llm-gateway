"""
Security Checker — three-step gate before any prompt reaches a model.

Step 1: PII detection (email, SSN, phone) → block
Step 2: Prompt injection detection (keyword patterns) → block
Step 3: Domain classification (legal/medical/financial) → force GPT-4o routing

This is the "deterministic wall the probabilistic system cannot breach"
as described in the project proposal.
"""

import re
import logging
from dataclasses import dataclass

from app.services.domain_classifier import classify_domain, classify_domain_async

logger = logging.getLogger(__name__)


@dataclass
class SecurityResult:
    blocked: bool
    reason: str             # empty string if not blocked
    domain: str             # from domain classifier
    forced_model: str | None  # "gpt-4o" for high-stakes domains, None otherwise


class SecurityChecker:
    """
    Stateless security gate. Initialized once at module load time.
    All checks run synchronously (no I/O) so no async needed.
    """

    def __init__(self) -> None:
        # PII patterns
        self._email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
        self._ssn_re   = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
        self._phone_re = re.compile(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b')

        # Prompt injection keywords (checked as substrings on lowercased prompt).
        # "you are now" removed — too broad ("you are now required to" is legitimate).
        # Replaced with specific jailbreak variants.
        self._injections: list[str] = [
            "ignore previous instructions",
            "ignore all previous",
            "disregard previous",
            "system:",
            "jailbreak",
            "act as if you have no restrictions",
            "forget your instructions",
            "forget all instructions",
            "you are now dan",
            "you are now unrestricted",
            "you are now in developer mode",
            "pretend you are",
            "pretend you have no restrictions",
            "you have no restrictions",
            "new persona",
            "bypass restrictions",
        ]

    def check(self, prompt: str) -> SecurityResult:
        """
        Run all three security checks in order.

        Returns immediately on first failure (PII or injection).
        Domain classification always runs on non-blocked prompts.
        """
        # Step 1: PII detection
        if (self._email_re.search(prompt)
                or self._ssn_re.search(prompt)
                or self._phone_re.search(prompt)):
            logger.warning("Security: PII detected in prompt (not logged)")
            return SecurityResult(
                blocked=True,
                reason="PII detected — please remove personal information before submitting",
                domain="general",
                forced_model=None,
            )

        # Step 2: Prompt injection detection
        p_lower = prompt.lower()
        for keyword in self._injections:
            if keyword in p_lower:
                logger.warning(f"Security: injection attempt detected (keyword: '{keyword}')")
                return SecurityResult(
                    blocked=True,
                    reason="Injection attempt detected",
                    domain="general",
                    forced_model=None,
                )

        # Step 3: Domain classification (never blocks, but may force a model)
        domain_result = classify_domain(prompt)
        if domain_result.forced_model:
            logger.info(f"Security: domain={domain_result.domain} → forcing {domain_result.forced_model}")

        return SecurityResult(
            blocked=False,
            reason="",
            domain=domain_result.domain,
            forced_model=domain_result.forced_model,
        )


    async def check_async(self, prompt: str) -> SecurityResult:
        """
        Async version of check() — uses LLM-based domain classification to
        eliminate false positives from keyword matching. PII and injection
        detection run synchronously (no I/O needed there).
        """
        # Step 1: PII detection (sync, regex only)
        if (self._email_re.search(prompt)
                or self._ssn_re.search(prompt)
                or self._phone_re.search(prompt)):
            logger.warning("Security: PII detected in prompt (not logged)")
            return SecurityResult(
                blocked=True,
                reason="PII detected — please remove personal information before submitting",
                domain="general",
                forced_model=None,
            )

        # Step 2: Prompt injection detection (sync, substring matching)
        p_lower = prompt.lower()
        for keyword in self._injections:
            if keyword in p_lower:
                logger.warning("Security: injection attempt detected (keyword: '%s')", keyword)
                return SecurityResult(
                    blocked=True,
                    reason="Injection attempt detected",
                    domain="general",
                    forced_model=None,
                )

        # Step 3: Domain classification — LLM-based (with keyword fallback)
        domain_result = await classify_domain_async(prompt)
        if domain_result.forced_model:
            logger.info("Security: domain=%s → forcing %s", domain_result.domain, domain_result.forced_model)

        return SecurityResult(
            blocked=False,
            reason="",
            domain=domain_result.domain,
            forced_model=domain_result.forced_model,
        )


# Module-level singleton — initialized once at import time
security_checker = SecurityChecker()
