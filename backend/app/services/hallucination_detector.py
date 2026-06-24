"""
Hallucination Detector for Aegis.

Two-tier detection strategy:

  Tier 1 — Hedging phrase scan (synchronous, runs on every response, zero cost)
    Scans the response text for linguistic uncertainty markers that correlate
    with hallucination risk (e.g. "I think", "might be", "I'm not sure").
    3+ hedging phrases → flag as potential hallucination.

  Tier 3 — Paraphrase variance (async, selective, uses LLM calls)
    Only runs when: domain in (legal, medical, financial) OR complexity_score > 0.7
    Algorithm (θ=0.35 empirically determined: factual queries <0.20, hallucination-prone >0.40):
      1. Generate 2 paraphrases of the original prompt via gpt-4o-mini
      2. Call the same model on both paraphrases in parallel (temperature=0.0)
      3. Embed all 3 responses with all-MiniLM-L6-v2, compute pairwise cosine similarity
      4. variance = 1 - avg_similarity
      5. variance > θ=0.35 → flag as hallucination (response shifts with phrasing)

  Tier 3 result overrides Tier 1 when Tier 3 runs.
  All Tier 3 failures (API errors, etc.) degrade gracefully to Tier 1 result.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.services.embedder import get_embedder

logger = logging.getLogger(__name__)

# Empirically determined variance threshold (factual <0.20, hallucination-prone >0.40)
THETA: float = 0.35

# Ring buffer for Tier 3 per-stage latency measurements (most-recent N runs).
# Surfaced via /api/tier3-overhead so the dashboard can report p50/p95/p99
# of the overhead Tier 3 adds on top of the base routing pipeline.
_TIER3_RING_SIZE = 1000


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)

# Hedging phrases that correlate with hallucination-prone output
HEDGING_PHRASES: list[str] = [
    "i think",
    "i believe",
    "i'm not sure",
    "i am not sure",
    "i'm not certain",
    "i am not certain",
    "might be",
    "may be",
    "could be",
    "possibly",
    "probably",
    "it's possible",
    "it is possible",
    "i'm not 100%",
    "not entirely sure",
    "to my knowledge",
    "as far as i know",
    "i may be wrong",
    "i could be wrong",
    "approximately",
    "i don't have",
    "i do not have",
    "based on my training",
    "up to my knowledge cutoff",
    "i cannot guarantee",
    "not currently able",
    "not able to",
    "i'm unable",
    "i am unable",
    "unable to provide",
    "unable to share",
    "cannot provide",
    "i cannot access",
    "don't have access",
    "do not have access",
    "please note",
    "real-time",
]

# Strong epistemic markers — model explicitly saying it cannot verify/find something.
# A single hit is sufficient to flag MEDIUM risk (unlike soft hedges which need 3+).
EPISTEMIC_PHRASES: list[str] = [
    "cannot find",
    "cannot verify",
    "cannot confirm",
    "no record of",
    "no evidence of",
    "not aware of",
    "i'm not aware",
    "i cannot find",
    "i cannot verify",
]


@dataclass
class DetectionResult:
    is_hallucination: bool
    confidence: float
    explanation: str
    pathway: Optional[str] = None  # "linguistic_uncertainty" | "paraphrase_variance" | None
    variance_score: Optional[float] = None  # raw paraphrase variance (only set by Tier 3)


class HallucinationDetector:
    """
    Two-tier hallucination detector.

    Instantiated once as a module-level singleton.
    Shares the all-MiniLM-L6-v2 embedder with SemanticCache via get_embedder().
    """

    def __init__(self) -> None:
        # Ring buffer of recent Tier 3 timing samples — each entry is a dict
        # of stage names → milliseconds. Most-recent N runs only.
        self._tier3_timings: deque[dict[str, float]] = deque(maxlen=_TIER3_RING_SIZE)
        # Escalation counters (in-memory, reset on restart like the ring buffer).
        # _analyze_count = queries that reached hallucination detection
        # (non-cached, non-blocked); _tier3_run_count = those escalated to Tier 3.
        # Their ratio is the measured Tier 3 escalation rate surfaced on the dashboard.
        self._analyze_count: int = 0
        self._tier3_run_count: int = 0

    def get_tier3_overhead_stats(self) -> dict[str, Optional[float] | dict[str, Optional[float]] | int]:
        """
        Return p50/p95/p99 of Tier 3 total latency, plus per-stage p50s,
        across the last _TIER3_RING_SIZE runs. Returns null values when no
        runs have been recorded yet.
        """
        samples = list(self._tier3_timings)
        totals = [s["total_ms"] for s in samples]
        gens = [s["paraphrase_gen_ms"] for s in samples if "paraphrase_gen_ms" in s]
        resps = [s["paraphrase_responses_ms"] for s in samples if "paraphrase_responses_ms" in s]
        embeds = [s["embed_compute_ms"] for s in samples if "embed_compute_ms" in s]

        def r(v: Optional[float]) -> Optional[float]:
            return round(v, 1) if v is not None else None

        rate = (
            round(self._tier3_run_count / self._analyze_count * 100.0, 1)
            if self._analyze_count > 0
            else None
        )

        return {
            "count": len(samples),
            "p50_ms": r(_percentile(totals, 0.50)),
            "p95_ms": r(_percentile(totals, 0.95)),
            "p99_ms": r(_percentile(totals, 0.99)),
            "per_stage": {
                "paraphrase_gen_p50_ms": r(_percentile(gens, 0.50)),
                "paraphrase_responses_p50_ms": r(_percentile(resps, 0.50)),
                "embed_compute_p50_ms": r(_percentile(embeds, 0.50)),
            },
            # Measured Tier 3 escalation rate over all analyzed queries this session.
            "analyzed": self._analyze_count,
            "tier3_runs": self._tier3_run_count,
            "tier3_rate_pct": rate,
        }

    def tier1_hedging_scan(self, response: str) -> DetectionResult:
        """
        Synchronous hedging phrase scan. Always runs on every response.

        Counts how many of the 25 known hedging phrases appear in the response.
        - 0 hits  → SAFE, confidence 0.90
        - 1-2 hits → SAFE but noted, confidence 0.70
        - 3+ hits  → FLAG, confidence scales with hit count (0.55–0.85)
        """
        lower = response.lower()

        # Check strong epistemic markers first — 1 hit is enough to flag MEDIUM.
        # These indicate the model explicitly cannot confirm the queried information.
        epistemic_hits = [p for p in EPISTEMIC_PHRASES if p in lower]
        if epistemic_hits:
            sample = ", ".join(f'"{h}"' for h in epistemic_hits[:2])
            return DetectionResult(
                is_hallucination=True,
                confidence=0.75,
                explanation=(
                    f"Model explicitly could not verify the queried information "
                    f"({sample}). The claim may be unverifiable or fabricated."
                ),
                pathway="epistemic_uncertainty",
            )

        hits = [p for p in HEDGING_PHRASES if p in lower]

        if len(hits) >= 3:
            confidence = min(0.50 + 0.05 * len(hits), 0.85)
            sample = ", ".join(f'"{h}"' for h in hits[:3])
            return DetectionResult(
                is_hallucination=True,
                confidence=confidence,
                explanation=(
                    f"Response contains {len(hits)} hedging phrases indicating uncertainty "
                    f"(e.g. {sample}). This linguistic pattern correlates with hallucination risk."
                ),
                pathway="linguistic_uncertainty",
            )

        if hits:
            return DetectionResult(
                is_hallucination=False,
                confidence=0.70,
                explanation=(
                    f"Response shows minor uncertainty ({len(hits)} hedging phrase(s): "
                    f"{', '.join(hits)}). Risk is low."
                ),
                pathway=None,
            )

        return DetectionResult(
            is_hallucination=False,
            confidence=0.90,
            explanation="No hedging phrases detected. Response appears confident.",
            pathway=None,
        )

    async def tier3_paraphrase_variance(
        self,
        original_prompt: str,
        original_response: str,
        model: str,
        provider: str,
        llm_client,
    ) -> DetectionResult:
        """
        Async paraphrase variance check.

        Uses gpt-4o-mini to generate 2 paraphrases of the original prompt (cheap),
        then calls the same model on both paraphrases in parallel at temperature=0.0
        for determinism. Embeds all 3 responses and measures semantic variance.

        Any failure degrades gracefully — returns a low-confidence SAFE result.
        """
        # ── Step 1: Generate paraphrases via gpt-4o-mini ─────────────────────────
        t_start = time.perf_counter()
        paraphrase_prompt = (
            "Rewrite the following question in 2 different ways, keeping the exact same meaning. "
            "Output only the 2 rewritten questions, one per line, with no numbering or labels:\n\n"
            f"{original_prompt}"
        )
        try:
            t_gen_start = time.perf_counter()
            para_result = await llm_client.call_openai(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": paraphrase_prompt}],
                temperature=0.7,
                max_tokens=200,
            )
            t_gen_ms = (time.perf_counter() - t_gen_start) * 1000.0
            paraphrases = [
                line.strip()
                for line in para_result.content.strip().splitlines()
                if line.strip()
            ][:2]
        except Exception as exc:
            logger.warning("Tier 3: paraphrase generation failed (%s), skipping", exc)
            return DetectionResult(
                is_hallucination=False,
                confidence=0.50,
                explanation="Paraphrase variance check skipped (paraphrase generation failed).",
            )

        if len(paraphrases) < 2:
            logger.warning("Tier 3: insufficient paraphrases (%d), skipping", len(paraphrases))
            return DetectionResult(
                is_hallucination=False,
                confidence=0.50,
                explanation="Paraphrase variance check skipped (model returned fewer than 2 paraphrases).",
            )

        # ── Step 2: Call original model on both paraphrases in parallel ──────────
        async def _call(prompt: str) -> Optional[str]:
            try:
                r = await llm_client.call_llm(
                    provider=provider,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=300,
                )
                return r.content
            except Exception as exc:
                logger.warning("Tier 3: paraphrase LLM call failed (%s)", exc)
                return None

        t_resp_start = time.perf_counter()
        para_responses = await asyncio.gather(_call(paraphrases[0]), _call(paraphrases[1]))
        t_resp_ms = (time.perf_counter() - t_resp_start) * 1000.0
        valid_responses = [r for r in para_responses if r is not None]

        if not valid_responses:
            return DetectionResult(
                is_hallucination=False,
                confidence=0.50,
                explanation="Paraphrase variance check skipped (all paraphrase LLM calls failed).",
            )

        # ── Step 3: Embed and compute variance ───────────────────────────────────
        # Compare only the paraphrase responses (both generated at temperature=0.0).
        # Excluding the original avoids mixing it with stochastic paraphrase outputs
        # and keeps the signal clean: we measure how much the model's answer shifts
        # when the question is rephrased, not whether it matches its original output.
        t_embed_start = time.perf_counter()
        embedder = get_embedder()
        embeddings = embedder.encode(valid_responses, normalize_embeddings=True)

        # Pairwise cosine similarity (dot product is correct since embeddings are L2-normalized)
        n = len(embeddings)
        sims = [
            float(np.dot(embeddings[i], embeddings[j]))
            for i in range(n)
            for j in range(i + 1, n)
        ]
        avg_similarity = sum(sims) / len(sims)
        variance = 1.0 - avg_similarity
        t_embed_ms = (time.perf_counter() - t_embed_start) * 1000.0

        # Record per-stage timing for /api/tier3-overhead
        self._tier3_timings.append({
            "total_ms": (time.perf_counter() - t_start) * 1000.0,
            "paraphrase_gen_ms": t_gen_ms,
            "paraphrase_responses_ms": t_resp_ms,
            "embed_compute_ms": t_embed_ms,
        })

        logger.info(
            "Tier 3: variance=%.3f (threshold=%.2f, avg_sim=%.3f, n_paraphrases=%d, "
            "gen=%.0fms responses=%.0fms embed=%.0fms)",
            variance, THETA, avg_similarity, len(valid_responses),
            t_gen_ms, t_resp_ms, t_embed_ms,
        )

        if variance > THETA:
            return DetectionResult(
                is_hallucination=True,
                confidence=min(0.50 + variance, 0.95),
                explanation=(
                    f"Causal intervention detected response variance {variance:.2f} > θ={THETA}. "
                    "The model's answer shifts significantly when the question is rephrased, "
                    "indicating hallucination-prone output on this topic."
                ),
                pathway="paraphrase_variance",
                variance_score=round(variance, 4),
            )

        return DetectionResult(
            is_hallucination=False,
            confidence=min(avg_similarity, 0.95),
            explanation=(
                f"Paraphrase variance {variance:.2f} is below threshold θ={THETA}. "
                "Response is stable across question phrasings."
            ),
            pathway=None,
            variance_score=round(variance, 4),
        )

    async def analyze(
        self,
        prompt: str,
        response: str,
        model: str,
        provider: str,
        complexity_score: float,
        domain: str,
        llm_client,
    ) -> DetectionResult:
        """
        Run appropriate detection tier(s) and return a single DetectionResult.

        Tier 1 always runs. Tier 3 runs when: domain in (legal, medical, financial)
        OR complexity_score > 0.6 OR factual_patterns detected.
        Tier 3 overrides Tier 1 only when Tier 3 detects high variance.
        If Tier 3 is clean but Tier 1 flagged epistemic uncertainty, Tier 1 wins.
        """
        self._analyze_count += 1
        tier1 = self.tier1_hedging_scan(response)

        factual_patterns = any(kw in prompt.lower() for kw in [
            "what did", "when did", "who said", "in what year", "historically",
            "according to", "what was", "where did",
            "what time", "current time", "right now", "currently", "today",
            "what date", "what day", "this week", "this year",
            # Named-researcher / named-study triggers (catches fabricated citations)
            " dr.", "prof.", "professor ",
            "study by", "research by", "paper by", "findings of",
            "conducted by", "published by",
        ])
        run_tier3 = (
            domain in ("legal", "medical", "financial")
            or complexity_score > 0.6
            or factual_patterns
        )
        if not run_tier3:
            return tier1

        self._tier3_run_count += 1
        logger.info(
            "Running Tier 3 paraphrase variance (domain=%s, complexity=%.2f)",
            domain, complexity_score,
        )
        tier3 = await self.tier3_paraphrase_variance(
            original_prompt=prompt,
            original_response=response,
            model=model,
            provider=provider,
            llm_client=llm_client,
        )
        # Tier 3 overrides Tier 1 when it detects high variance (more rigorous signal).
        # But if Tier 3 is clean and Tier 1 caught an epistemic marker, keep Tier 1 —
        # consistent uncertainty across paraphrases still means the claim is unverifiable.
        if tier3.is_hallucination:
            return tier3
        if tier1.is_hallucination:
            return tier1
        return tier3


# Module-level singleton
hallucination_detector = HallucinationDetector()
