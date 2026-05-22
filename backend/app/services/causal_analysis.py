"""
Domain-cost subgroup breakdown for the /api/domain-cost-breakdown endpoint.

Descriptive analytics — not causal inference. Reports the average per-request
routing cost for sensitive-domain queries (legal/medical/financial) vs general
queries, stratified by complexity tier.

The domain hard-gate is deterministic: sensitive domains are unconditionally
routed to gpt-4o. The cost delta is therefore mechanically expected by design
of the routing rule. This endpoint exposes the magnitude of that delta as
descriptive telemetry, not as a causal estimate — running formal causal
inference on this signal would be circular, validating only that the code
implements its own routing rule.

This module previously ran a DoWhy backdoor regression with a placebo refuter.
The placebo refuter was removed for performance (commit e41b454), and the
regression has now been replaced with a transparent pandas.groupby in line
with the honest-framing pass.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SENSITIVE_DOMAINS = {"legal", "medical", "financial"}

# Complexity tier bands — match the live routing classifier in app/services/classifier.py
_TIERS = [
    ("low",  0.00, 0.45),
    ("mid",  0.45, 0.65),
    ("high", 0.65, 0.80),
    ("top",  0.80, 1.01),
]


def _empty_result(note: str, n: int = 0, n_sensitive: int = 0, n_general: int = 0) -> dict[str, Any]:
    return {
        "n": n,
        "n_sensitive_domain": n_sensitive,
        "n_general": n_general,
        "tiers": [],
        "cost_delta_usd": None,
        "avg_cost_sensitive": None,
        "avg_cost_general": None,
        "method": "subgroup_mean_comparison",
        "note": note,
    }


def _compute_breakdown(rows: list[dict]) -> dict[str, Any]:
    import pandas as pd

    if not rows:
        return _empty_result(
            "No requests yet — make a few queries to populate the breakdown."
        )

    df = pd.DataFrame(rows)
    df["is_sensitive_domain"] = df["domain"].isin(_SENSITIVE_DOMAINS)
    df["cost_usd"] = pd.to_numeric(df["cost_usd"], errors="coerce").fillna(0.0)
    df["complexity_score"] = pd.to_numeric(df["complexity_score"], errors="coerce").fillna(0.5)

    n_sensitive = int(df["is_sensitive_domain"].sum())
    n_general = len(df) - n_sensitive

    if n_sensitive == 0 or n_general == 0:
        return _empty_result(
            f"Need both sensitive-domain and general requests to compute a delta. "
            f"Currently {n_sensitive} sensitive, {n_general} general.",
            n=len(df), n_sensitive=n_sensitive, n_general=n_general,
        )

    sensitive_mean = float(df.loc[df["is_sensitive_domain"], "cost_usd"].mean())
    general_mean = float(df.loc[~df["is_sensitive_domain"], "cost_usd"].mean())
    overall_delta = sensitive_mean - general_mean

    tiers: list[dict[str, Any]] = []
    for name, lo, hi in _TIERS:
        bin_df = df[(df["complexity_score"] >= lo) & (df["complexity_score"] < hi)]
        s_rows = bin_df[bin_df["is_sensitive_domain"]]
        g_rows = bin_df[~bin_df["is_sensitive_domain"]]

        avg_s = float(s_rows["cost_usd"].mean()) if len(s_rows) > 0 else None
        avg_g = float(g_rows["cost_usd"].mean()) if len(g_rows) > 0 else None
        delta = (avg_s - avg_g) if (avg_s is not None and avg_g is not None) else None

        tiers.append({
            "tier": name,
            "range": f"[{lo:.2f}, {hi:.2f})",
            "n_sensitive": int(len(s_rows)),
            "n_general": int(len(g_rows)),
            "avg_cost_sensitive": round(avg_s, 6) if avg_s is not None else None,
            "avg_cost_general": round(avg_g, 6) if avg_g is not None else None,
            "cost_delta": round(delta, 6) if delta is not None else None,
        })

    return {
        "n": len(df),
        "n_sensitive_domain": n_sensitive,
        "n_general": n_general,
        "tiers": tiers,
        "cost_delta_usd": round(overall_delta, 6),
        "avg_cost_sensitive": round(sensitive_mean, 6),
        "avg_cost_general": round(general_mean, 6),
        "method": "subgroup_mean_comparison",
        "note": (
            f"Sensitive-domain queries cost ${overall_delta:.5f}/req more than general queries "
            f"on average (n={len(df)}, sensitive={n_sensitive}, general={n_general}). "
            f"This delta is mechanically expected by design — sensitive domains are unconditionally "
            f"routed to gpt-4o by the hard-gate. Reported as descriptive telemetry, not a causal estimate."
        ),
    }


async def run_domain_cost_breakdown(rows: list[dict]) -> dict[str, Any]:
    """Run the subgroup breakdown in a thread (pandas operations release the GIL)."""
    return await asyncio.to_thread(_compute_breakdown, rows)
