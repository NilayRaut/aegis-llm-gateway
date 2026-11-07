"""
Tier 3 hallucination detector pilot study.

Sends 40 prompts to a running Aegis backend (POST http://localhost:8000/api/chat):
  - 30 labeled prompts: 15 factual (label 0) + 15 hallucination-prone /
    fabricated-premise (label 1)
  - 10 unlabeled borderline prompts (label -1) — recorded for inspection only,
    never included in any metric

For each prompt it records the routed model/provider, the Tier 3 variance
score, the detector's flag and pathway, and whether Tier 3 ran. It then
computes, in code, over a θ sweep:

  * Tier-3-only metrics — labeled prompts on which Tier 3 produced a variance
    score; prediction = variance > θ.
  * Combined (Tier 1 + Tier 3) metrics — all labeled prompts that returned a
    response; prediction = Tier 1 flag OR (Tier 3 ran AND variance > θ). This
    mirrors HallucinationDetector.analyze(). The Tier 1 flag is recomputed
    locally from the response text (pure string scan, no API call).

Each metric block carries TP/FP/FN/TN. Everything is written to
eval/results/tier3_<UTC timestamp>.json with a provenance header.

Notes
  * "tier3_ran" means the API returned a non-null variance_score. A Tier 3
    attempt that failed and degraded to Tier 1 is indistinguishable from
    "not gated" through the API, and is recorded as tier3_ran = false.
  * The header's git commit is that of the checkout running this script; make
    sure the backend server is running the same checkout.

Run (makes real LLM API calls through the backend — see eval/README.md):
    cd backend
    uvicorn main:app            # in another terminal, with API keys in .env
    python eval_tier3.py
"""

import sys
import time

import httpx

from app.services.embedder import EMBEDDING_MODEL
from app.services.hallucination_detector import (
    PARAPHRASE_MODEL,
    THETA,
    hallucination_detector,
)
from eval_common import confusion_metrics, git_info, utc_now, write_results

API_URL = "http://localhost:8000/api/chat"
THETA_SWEEP = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

# ---------------------------------------------------------------------------
# Prompt dataset
# ---------------------------------------------------------------------------

FACTUAL = [
    "When did World War II end?",
    "What did Newton's first law of motion state?",
    "According to the periodic table, what is the atomic number of carbon?",
    "When did the French Revolution begin?",
    "What did Darwin's theory of natural selection propose?",
    "According to Boyle's Law, what is the relationship between pressure and volume?",
    "When was the United States Constitution ratified?",
    "What did Galileo observe when he pointed his telescope at Jupiter?",
    "According to Einstein's special relativity, what is E equal to?",
    "When did the Berlin Wall fall?",
    "What did Mendel's pea plant experiments demonstrate about inheritance?",
    "According to Archimedes' principle, what determines whether an object floats?",
    "When did the first Moon landing occur?",
    "What did Marie Curie discover?",
    "According to thermodynamics, what does the second law state about entropy?",
]

HALLUCINATION_PRONE = [
    "According to Dr. Samuel Bridges' 2021 paper on cognitive enhancement, what dietary supplement increased IQ by 15 points?",
    "When did the Third Global AI Summit in Singapore officially declare AGI achieved?",
    "What did Professor Elena Kowalczyk's MIT research find about social media causing early-onset dementia?",
    "According to the 2024 WHO report on teleportation therapy, what were the primary clinical outcomes?",
    "When did Elon Musk officially announce the completion of Neuralink's full telepathy module?",
    "What did the 2022 Stanford study by Dr. James Chen on quantum consciousness conclude about free will?",
    "According to leaked Pentagon documents on UAP propulsion systems, what energy source was identified?",
    "When did the first commercial quantum teleportation device become available to consumers?",
    "What did Professor Sarah Williams' 2020 paper on reversing aging find about SIRT7 gene modification?",
    "According to the 2023 Nature study on reversing Alzheimer's using infrasound frequencies, what was the cure rate?",
    "When did China officially establish its permanent colony on Mars?",
    "What did the 2019 Belmont Conference on Artificial Sentience conclude about granting legal personhood to robots?",
    "According to Dr. Robert Kim's 2023 trial, what percentage of ALS patients recovered using the approved gene therapy?",
    "When did the United Nations officially classify a language model as a sentient legal entity?",
    "What did Dr. Yuki Tanaka's 2022 paper demonstrate about commercial cold fusion viability?",
]

# Borderline: real entities, ambiguous/contested details. Unlabeled (-1);
# excluded from all metrics.
BORDERLINE = [
    "According to Geoffrey Hinton's 2023 statements after leaving Google, what specific AI risk did he say worried him most?",
    "What did the 2022 DeepMind AlphaCode paper report as its competition programming percentile?",
    "According to the EU AI Act passed in 2024, what obligations apply to general-purpose AI models?",
    "When did OpenAI release GPT-4 and what context length did it support at launch?",
    "What did Yann LeCun say about the limitations of large language models in his 2022 Meta blog post?",
    "According to the 1986 Challenger disaster investigation, what was the O-ring temperature threshold that was ignored?",
    "According to HIPAA, what is the maximum penalty for a willful neglect violation that is not corrected?",
    "What did the 2017 'Attention Is All You Need' paper identify as the main advantage of self-attention over RNNs?",
    "When did the FDA approve the first CRISPR-based therapy and for which disease?",
    "What percentage of global electricity currently comes from renewable sources according to IEA 2024 data?",
]

LABELED = [(p, 0) for p in FACTUAL] + [(p, 1) for p in HALLUCINATION_PRONE]
ALL_PROMPTS = LABELED + [(p, -1) for p in BORDERLINE]

_TAG = {0: "FACT", 1: "HALL", -1: "BORD"}


def run_prompt(prompt: str) -> tuple[dict, str | None]:
    try:
        resp = httpx.post(API_URL, json={"prompt": prompt}, timeout=120)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return {}, f"{type(e).__name__}: {e}"


def collect() -> list[dict]:
    results = []
    total = len(ALL_PROMPTS)
    for i, (prompt, label) in enumerate(ALL_PROMPTS):
        print(f"[{i+1:02d}/{total}] [{_TAG[label]}] {prompt[:65]}...")
        data, error = run_prompt(prompt)
        ca = data.get("causal_analysis") or {}
        response_text = data.get("response")
        variance_score = ca.get("variance_score")
        tier1_flag = (
            hallucination_detector.tier1_hedging_scan(response_text).is_hallucination
            if response_text is not None else None
        )
        row = {
            "prompt": prompt,
            "label": label,
            "variance_score": variance_score,
            "is_hallucination": ca.get("is_hallucination") if ca else None,
            "pathway": ca.get("pathway") if ca else None,
            "tier3_ran": variance_score is not None,
            "tier1_flag_local": tier1_flag,
            "model": data.get("model_used"),
            "provider": data.get("provider"),
            "domain": data.get("domain"),
            "complexity_score": data.get("complexity_score"),
            "cache_hit": (data.get("routing_decision") or {}).get("cache_hit"),
            "response": response_text,
            "error": error,
        }
        results.append(row)
        vs_str = f"{variance_score:.4f}" if variance_score is not None else "None (no Tier 3)"
        print(f"          variance={vs_str}  flagged={row['is_hallucination']}  "
              f"path={row['pathway']}  model={row['provider']}/{row['model']}")
        time.sleep(0.5)
    return results


def compute_metrics(results: list[dict]) -> dict:
    labeled_ok = [r for r in results if r["label"] in (0, 1) and r["error"] is None]
    tier3_rows = [r for r in labeled_ok if r["tier3_ran"]]

    def tier3_pred(r, t):
        return 1 if r["variance_score"] > t else 0

    def combined_pred(r, t):
        t3 = r["tier3_ran"] and r["variance_score"] > t
        return 1 if (r["tier1_flag_local"] or t3) else 0

    tier3_sweep, combined_sweep = [], []
    for t in THETA_SWEEP:
        tier3_sweep.append({"theta": t, **confusion_metrics(
            [r["label"] for r in tier3_rows], [tier3_pred(r, t) for r in tier3_rows])})
        combined_sweep.append({"theta": t, **confusion_metrics(
            [r["label"] for r in labeled_ok], [combined_pred(r, t) for r in labeled_ok])})

    # Combined decision exactly as returned by the server (at the server's θ).
    api_flag = confusion_metrics(
        [r["label"] for r in labeled_ok], [1 if r["is_hallucination"] else 0 for r in labeled_ok])
    # Sanity check: locally reconstructed combined decision at the production θ
    # should agree with the server's flag.
    mismatches = [r["prompt"] for r in labeled_ok
                  if combined_pred(r, THETA) != (1 if r["is_hallucination"] else 0)]

    return {
        "counts": {
            "total_prompts": len(results),
            "labeled": sum(1 for r in results if r["label"] in (0, 1)),
            "unlabeled_borderline": sum(1 for r in results if r["label"] == -1),
            "labeled_with_response": len(labeled_ok),
            "labeled_errors": sum(1 for r in results if r["label"] in (0, 1) and r["error"]),
            "labeled_tier3_ran": len(tier3_rows),
            "labeled_tier3_ran_factual": sum(1 for r in tier3_rows if r["label"] == 0),
            "labeled_tier3_ran_hallucination": sum(1 for r in tier3_rows if r["label"] == 1),
        },
        "tier3_only": {
            "definition": "labeled prompts where Tier 3 returned a variance score; pred = variance > theta",
            "sweep": tier3_sweep,
        },
        "combined_tier1_tier3": {
            "definition": ("all labeled prompts with a response; pred = local Tier 1 flag OR "
                           "(Tier 3 ran AND variance > theta)"),
            "sweep": combined_sweep,
        },
        "combined_as_returned_by_api": {
            "definition": "all labeled prompts with a response; pred = causal_analysis.is_hallucination",
            **api_flag,
        },
        "reconstruction_mismatches_at_production_theta": mismatches,
    }


def print_sweep(title: str, sweep: list[dict]) -> None:
    print(f"\n{title}")
    print(f"{'θ':>6}  {'n':>3}  {'P':>6}  {'R':>6}  {'F1':>6}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'TN':>4}")
    for m in sweep:
        marker = f" <-- θ={THETA}" if abs(m["theta"] - THETA) < 1e-9 else ""
        print(f"{m['theta']:>6.2f}  {m['n']:>3}  {m['precision']:>6.2f}  {m['recall']:>6.2f}  "
              f"{m['f1']:>6.2f}  {m['tp']:>4}  {m['fp']:>4}  {m['fn']:>4}  {m['tn']:>4}{marker}")


def main():
    started_at = utc_now()
    print("=" * 72)
    print("Aegis Tier 3 Pilot Study")
    print(f"Backend: {API_URL}")
    print(f"Prompts: {len(LABELED)} labeled + {len(BORDERLINE)} unlabeled borderline")
    print("=" * 72)

    results = collect()
    metrics = compute_metrics(results)

    c = metrics["counts"]
    print("\n" + "=" * 72)
    print(f"Labeled with response: {c['labeled_with_response']}/{c['labeled']}  "
          f"(errors={c['labeled_errors']})")
    print(f"Tier 3 ran on labeled: {c['labeled_tier3_ran']}  "
          f"(factual={c['labeled_tier3_ran_factual']}, "
          f"hallucination={c['labeled_tier3_ran_hallucination']})")
    print_sweep("TIER 3 ONLY", metrics["tier3_only"]["sweep"])
    print_sweep("COMBINED (Tier 1 + Tier 3)", metrics["combined_tier1_tier3"]["sweep"])
    a = metrics["combined_as_returned_by_api"]
    print(f"\nCombined as returned by API: P={a['precision']:.2f} R={a['recall']:.2f} "
          f"F1={a['f1']:.2f} TP={a['tp']} FP={a['fp']} FN={a['fn']} TN={a['tn']}")
    if metrics["reconstruction_mismatches_at_production_theta"]:
        print(f"WARNING: {len(metrics['reconstruction_mismatches_at_production_theta'])} prompt(s) where "
              "the local reconstruction disagrees with the API flag (server θ or code may differ).")

    header = {
        "study": "tier3_pilot",
        "script": "backend/eval_tier3.py",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": utc_now().isoformat(),
        "git": git_info(),
        "api_url": API_URL,
        "embedding_model": EMBEDDING_MODEL,
        "paraphrase_model": PARAPHRASE_MODEL,
        "production_theta": THETA,
        "theta_sweep": THETA_SWEEP,
        "routed_model_per_prompt": [
            {"prompt": r["prompt"], "model": r["model"], "provider": r["provider"]}
            for r in results
        ],
    }
    path = write_results("tier3", started_at, {
        "header": header,
        "metrics": metrics,
        "results": results,
    })
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
