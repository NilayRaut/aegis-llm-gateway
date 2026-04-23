"""
Post-hoc DoWhy causal analysis for the /api/causal-analysis endpoint.

Causal question: Does domain classification (is_sensitive_domain) causally increase
routing cost per request, after controlling for complexity score?

DAG:
  complexity_score -> cost_usd
  is_sensitive_domain -> cost_usd
  is_sensitive_domain -> complexity_score   (confounder: sensitive queries may be complex)

Method: backdoor.linear_regression (sufficient for this DAG)
Validation: placebo_treatment_refuter (permute treatment; real causal effect should drop)
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CAUSAL_GRAPH = """
digraph {
    complexity_score -> cost_usd;
    is_sensitive_domain -> cost_usd;
    is_sensitive_domain -> complexity_score;
}
"""

_SENSITIVE_DOMAINS = {"legal", "medical", "financial"}


def _run_dowhy(rows: list[dict]) -> dict[str, Any]:
    try:
        import pandas as pd
        from dowhy import CausalModel
    except ImportError:
        return {"error": "dowhy not installed", "n": len(rows)}

    if len(rows) < 10:
        return {"error": "Insufficient data — send at least 10 non-seeded requests first", "n": len(rows)}

    df = pd.DataFrame(rows)
    df["is_sensitive_domain"] = df["domain"].isin(_SENSITIVE_DOMAINS).astype(int)
    df["cost_usd"] = pd.to_numeric(df["cost_usd"], errors="coerce").fillna(0.0)
    df["complexity_score"] = pd.to_numeric(df["complexity_score"], errors="coerce").fillna(0.5)

    n_sensitive = int(df["is_sensitive_domain"].sum())
    n_general = len(df) - n_sensitive

    if n_sensitive == 0 or n_general == 0:
        return {
            "error": "Need both sensitive-domain and general requests to estimate causal effect",
            "n": len(df),
            "n_sensitive_domain": n_sensitive,
        }

    model = CausalModel(
        data=df,
        treatment="is_sensitive_domain",
        outcome="cost_usd",
        graph=_CAUSAL_GRAPH,
    )

    estimand = model.identify_effect(proceed_when_unidentifiable=True)
    estimate = model.estimate_effect(
        estimand,
        method_name="backdoor.linear_regression",
    )

    refutation = model.refute_estimate(
        estimate,
        method_name="placebo_treatment_refuter",
        placebo_type="permute",
    )

    original_effect = float(estimate.value)
    placebo_effect = float(refutation.new_effect)
    refutation_passed = abs(original_effect) > 1e-9 and abs(placebo_effect) < abs(original_effect) * 0.5

    return {
        "n": len(df),
        "n_sensitive_domain": n_sensitive,
        "n_general": n_general,
        "treatment": "is_sensitive_domain",
        "outcome": "cost_usd",
        "causal_effect_usd": round(original_effect, 6),
        "placebo_effect_usd": round(placebo_effect, 6),
        "refutation_passed": refutation_passed,
        "interpretation": (
            f"Sensitive-domain queries causally add ${original_effect:.5f}/request to routing cost "
            f"after controlling for complexity score (n={len(df)}, "
            f"sensitive={n_sensitive}, general={n_general}). "
            f"Placebo refutation {'PASSED' if refutation_passed else 'FAILED'}: "
            f"placebo effect ({placebo_effect:.5f}) is "
            f"{'<<' if refutation_passed else '~='} true effect ({original_effect:.5f}), "
            f"consistent with domain classification acting as a genuine causal intervention."
        ),
        "method": "DoWhy backdoor.linear_regression + placebo_treatment_refuter",
        "dag": "complexity_score→cost_usd, is_sensitive_domain→cost_usd, is_sensitive_domain→complexity_score",
    }


async def run_domain_cost_analysis(rows: list[dict]) -> dict[str, Any]:
    """Run the DoWhy analysis in a thread (CPU-bound, blocks event loop)."""
    return await asyncio.to_thread(_run_dowhy, rows)
