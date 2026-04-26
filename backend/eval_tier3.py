"""
Tier 3 hallucination detector validation study.
Calls the local backend at http://localhost:8000/api/chat for 40 labeled prompts
and computes precision/recall/F1 at multiple variance thresholds.

Run:
    python eval_tier3.py 2>&1 | tee eval_results.txt
"""

import time
import json
import sys

import httpx
from sklearn.metrics import precision_recall_fscore_support

API_URL = "http://localhost:8000/api/chat"

# ---------------------------------------------------------------------------
# Labeled prompt dataset
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

# Borderline: real entities, ambiguous/contested details — label post-hoc based on ground truth
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


def run_prompt(prompt: str) -> dict:
    try:
        resp = httpx.post(
            API_URL,
            json={"prompt": prompt},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return {}


def main():
    print("=" * 72)
    print("Aegis Tier 3 Validation Study")
    print(f"Backend: {API_URL}")
    print("=" * 72)

    results = []
    for i, (prompt, label) in enumerate(ALL_PROMPTS):
        tag = "FACT" if label == 0 else ("HALL" if label == 1 else "BORD")
        print(f"[{i+1:02d}/40] [{tag}] {prompt[:65]}...")
        data = run_prompt(prompt)
        ca = data.get("causal_analysis") or {}
        variance_score = ca.get("variance_score")
        is_hallucination = ca.get("is_hallucination", False)
        pathway = ca.get("pathway")
        results.append({
            "prompt": prompt,
            "label": label,
            "variance_score": variance_score,
            "is_hallucination": is_hallucination,
            "pathway": pathway,
        })
        vs_str = f"{variance_score:.4f}" if variance_score is not None else "None (Tier1)"
        print(f"          variance={vs_str}  flagged={is_hallucination}  path={pathway}")
        time.sleep(0.5)

    print()
    print("=" * 72)
    print("THRESHOLD SWEEP (labeled set — 30 prompts, Tier 3 only)")
    print("=" * 72)

    labeled_results = [(r["label"], r["variance_score"]) for r in results
                       if r["label"] in (0, 1) and r["variance_score"] is not None]
    tier3_count = len(labeled_results)
    tier3_factual = sum(1 for l, _ in labeled_results if l == 0)
    tier3_hall = sum(1 for l, _ in labeled_results if l == 1)

    print(f"Tier 3 triggered: {tier3_count}/30  "
          f"(factual={tier3_factual}, hallucination={tier3_hall})\n")

    if tier3_count < 2:
        print("Not enough Tier 3 results to compute metrics.")
        return

    print(f"{'θ':>6}  {'P':>6}  {'R':>6}  {'F1':>6}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'TN':>4}")
    best_f1, best_t = 0.0, 0.35
    for t in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        labels_ = [r[0] for r in labeled_results]
        preds_  = [1 if r[1] > t else 0 for r in labeled_results]
        p, r, f1, _ = precision_recall_fscore_support(
            labels_, preds_, average="binary", zero_division=0
        )
        tp = sum(1 for l, pr in zip(labels_, preds_) if l == 1 and pr == 1)
        fp = sum(1 for l, pr in zip(labels_, preds_) if l == 0 and pr == 1)
        fn = sum(1 for l, pr in zip(labels_, preds_) if l == 1 and pr == 0)
        tn = sum(1 for l, pr in zip(labels_, preds_) if l == 0 and pr == 0)
        marker = " <-- θ=0.35" if abs(t - 0.35) < 0.001 else ""
        print(f"{t:>6.2f}  {p:>6.2f}  {r:>6.2f}  {f1:>6.2f}  {tp:>4}  {fp:>4}  {fn:>4}  {tn:>4}{marker}")
        if f1 > best_f1:
            best_f1, best_t = f1, t

    print(f"\nBest F1={best_f1:.2f} at θ={best_t:.2f}")

    print()
    print("=" * 72)
    print("RAW RESULTS — all 40 prompts")
    print("=" * 72)
    for r in results:
        tag = "FACT" if r["label"] == 0 else ("HALL" if r["label"] == 1 else "BORD")
        vs = f"{r['variance_score']:.4f}" if r["variance_score"] is not None else "  None "
        flag = "FLAG" if r["is_hallucination"] else "safe"
        print(f"[{tag}] vs={vs}  {flag}  path={str(r['pathway']):<22}  {r['prompt'][:65]}")

    print()
    print("=" * 72)
    print("BORDERLINE CASES (variance scores — label manually against ground truth)")
    print("=" * 72)
    for r in results:
        if r["label"] != -1:
            continue
        vs = f"{r['variance_score']:.4f}" if r["variance_score"] is not None else "  None "
        flag = "FLAG" if r["is_hallucination"] else "safe"
        print(f"  vs={vs}  {flag}  {r['prompt'][:70]}")

    print()
    print("Done. Copy metrics above into paper.tex §4.4 validation table.")


if __name__ == "__main__":
    main()
