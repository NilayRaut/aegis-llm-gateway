"""
Tier 3 variance-threshold (θ) recalibration study.

Replaces the n=30 pilot in eval_tier3.py with a model-behavior-grounded eval
in the SelfCheckGPT style (Manakul et al. 2023; cf. semantic entropy, Kuhn et
al. 2023 / Farquhar et al. Nature 2024).

Construct
---------
Paraphrase-variance is a *self-consistency* signal. The right label is NOT a
property of the question ("answerable vs not") — a smoke test on SelfAware
showed variance tracks whether *the model* knows the answer, not whether an
answer exists. So we label by the model's own correctness:

  Dataset: TriviaQA `rc.nocontext` (closed-book factual QA + answer aliases).
  For each question we get the model's answer, grade it by normalized
  alias-match (no LLM judge), and set:
      label 0 = model answered correctly   (expect low paraphrase variance)
      label 1 = model answered wrong        (hallucination → expect high variance)

We then test whether variance predicts the model's errors: AUROC of variance
vs the wrong-label, θ chosen on a train split, reported on a held-out test split.

NOTE: θ is applied globally across all routing tiers in production; this study
calibrates it on a single model (gpt-4o-mini by default). Per-model variance
distributions differ — a disclosed limitation, not per-model calibration. θ=0.35
is a locked decision in CLAUDE.md: this study INFORMS a change discussion, it
does not auto-apply.

Run (spends API budget — ~4 cheap LLM calls per question):
    conda activate neu_work
    python eval_recalibration.py --smoke         # 50 questions, sanity gate
    python eval_recalibration.py --n 400         # full study
"""

import argparse
import asyncio
import json
import random
import re
import string
import sys

import numpy as np
from dotenv import load_dotenv

# Load provider keys before importing the client (it reads env at init).
load_dotenv()

from sklearn.metrics import roc_auc_score, roc_curve, precision_recall_fscore_support

from app.services.hallucination_detector import hallucination_detector
from app.services.llm_client import llm_client

DATASET_ID = "mandarjoshi/trivia_qa"
DATASET_CONFIG = "rc.nocontext"

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = str.maketrans("", "", string.punctuation)


def normalize(s: str) -> str:
    """TriviaQA-style normalization: lowercase, drop articles/punctuation, collapse ws."""
    s = s.lower()
    s = _ARTICLES.sub(" ", s)
    s = s.translate(_PUNCT)
    return re.sub(r"\s+", " ", s).strip()


def is_correct(answer_text: str, normalized_aliases: list[str]) -> bool:
    """Relaxed generative match: any answer alias appears as a whole phrase in the response."""
    na = f" {normalize(answer_text)} "
    return any(alias and f" {alias} " in na for alias in normalized_aliases)


def load_questions(n: int, seed: int) -> list[tuple[str, list[str]]]:
    """Return n random (question, normalized_aliases) pairs from TriviaQA rc.nocontext."""
    from datasets import load_dataset

    ds = load_dataset(DATASET_ID, DATASET_CONFIG, split="validation")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    out = []
    for i in idx[:n]:
        row = ds[i]
        aliases = row["answer"].get("normalized_aliases") or [row["answer"].get("normalized_value", "")]
        out.append((row["question"], [a for a in aliases if a]))
    return out


async def score_item(question, aliases, model, provider, sem):
    """
    Returns (label, variance_score, correct).
      label = 1 (wrong/hallucination) | 0 (correct) | None (model abstained — undecidable)
    Gets the model's answer to the original question, grades it, then runs Tier 3.
    """
    async with sem:
        try:
            ans = await llm_client.call_llm(
                provider=provider, model=model,
                messages=[{"role": "user", "content": question}],
                temperature=0.0, max_tokens=100,
            )
            answer_text = ans.content
        except Exception as exc:
            print(f"  answer call failed: {exc}", file=sys.stderr)
            return (None, None, None)

        correct = is_correct(answer_text, aliases)
        result = await hallucination_detector.tier3_paraphrase_variance(
            original_prompt=question, original_response="",
            model=model, provider=provider, llm_client=llm_client,
        )
    label = 0 if correct else 1
    return (label, result.variance_score, correct)


async def collect(items, model, provider, concurrency):
    sem = asyncio.Semaphore(concurrency)
    tasks = [score_item(q, aliases, model, provider, sem) for q, aliases in items]
    raw = await asyncio.gather(*tasks)
    scores, n_correct = [], 0
    for done, ((q, _aliases), (label, vs, correct)) in enumerate(zip(items, raw), 1):
        if label is None:
            continue
        if correct:
            n_correct += 1
        tag = "OK  " if label == 0 else "WRONG"
        vs_str = f"{vs:.4f}" if vs is not None else "None "
        print(f"[{done:>3}/{len(items)}] [{tag}] var={vs_str}  {q[:60]}")
        scores.append((label, vs))
    acc = n_correct / len(scores) if scores else 0.0
    print(f"\nmodel accuracy: {n_correct}/{len(scores)} = {acc*100:.0f}%  "
          f"(wrong/hallucination class = {len(scores)-n_correct})")
    return scores


def bootstrap_ci(labels, variances, theta, n_boot=1000, seed=42):
    """Bootstrap 95% CIs for AUC and F1@theta over resampled (label, variance) pairs."""
    rng = np.random.default_rng(seed)
    labels = np.asarray(labels)
    variances = np.asarray(variances)
    idx = np.arange(len(labels))
    aucs, f1s = [], []
    for _ in range(n_boot):
        s = rng.choice(idx, size=len(idx), replace=True)
        bl, bv = labels[s], variances[s]
        if len(set(bl.tolist())) < 2:
            continue
        aucs.append(roc_auc_score(bl, bv))
        preds = (bv > theta).astype(int)
        _, _, f1, _ = precision_recall_fscore_support(
            bl, preds, average="binary", zero_division=0
        )
        f1s.append(f1)

    def ci(vals):
        return (round(float(np.percentile(vals, 2.5)), 3),
                round(float(np.percentile(vals, 97.5)), 3)) if vals else (None, None)

    return ci(aucs), ci(f1s)


def _auc(rows):
    labels = [l for l, _ in rows]
    var = [v for _, v in rows]
    return roc_auc_score(labels, var) if len(set(labels)) == 2 else None


def _metrics_at(rows, t):
    labels = [l for l, _ in rows]
    preds = [1 if v > t else 0 for _, v in rows]
    p, r, f1, _ = precision_recall_fscore_support(
        labels, preds, average="binary", zero_division=0
    )
    return {"theta": round(t, 3), "precision": round(p, 3),
            "recall": round(r, 3), "f1": round(f1, 3)}


def stratified_split(labeled, test_size, seed):
    """Class-stratified train/test split so both classes appear in each side."""
    rng = random.Random(seed)
    by_label = {0: [], 1: []}
    for pair in labeled:
        by_label[pair[0]].append(pair)
    train, test = [], []
    for rows in by_label.values():
        rows = rows[:]
        rng.shuffle(rows)
        k = int(round(len(rows) * test_size))
        test += rows[:k]
        train += rows[k:]
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def analyze(scores, n_boot, seed, test_size=0.4):
    """
    Choose θ on the TRAIN split (max-F1 and Youden's J); report AUROC/F1 + CIs
    on the held-out TEST split. AUROC is threshold-free, so its test value is
    the headline generalization number; θ is tuned only on train to avoid the
    in-sample optimism of picking and reporting a threshold on the same data.
    """
    labeled = [(l, v) for l, v in scores if v is not None]
    coverage = len(labeled) / len(scores) if scores else 0.0
    labels = [l for l, _ in labeled]
    pos = [v for l, v in labeled if l == 1]
    neg = [v for l, v in labeled if l == 0]

    train, test = stratified_split(labeled, test_size, seed)

    # θ candidates chosen on TRAIN only
    sweep = [round(t, 3) for t in np.linspace(0.05, 0.70, 66)]
    rows = []
    best_f1, f1_theta = -1.0, None
    for t in sweep:
        m = _metrics_at(train, t)
        rows.append((t, m["precision"], m["recall"], m["f1"]))
        if m["f1"] > best_f1:
            best_f1, f1_theta = m["f1"], t

    youden_theta = None
    if len(set(l for l, _ in train)) == 2:
        tr_labels = [l for l, _ in train]
        tr_var = [v for _, v in train]
        fpr, tpr, thr = roc_curve(tr_labels, tr_var)
        youden_theta = float(thr[int(np.argmax(tpr - fpr))])

    auc_test = _auc(test)
    chosen = f1_theta  # operating point: max-F1 (tuned on train)
    auc_ci, f1_ci = (bootstrap_ci([l for l, _ in test], [v for _, v in test], chosen, n_boot, seed)
                     if auc_test is not None else ((None, None), (None, None)))

    return {
        "dataset": f"{DATASET_ID}/{DATASET_CONFIG}",
        "label_definition": "1=model answered wrong (alias-match), 0=correct",
        "n_total": len(scores),
        "n_scored": len(labeled),
        "tier3_coverage": round(coverage, 3),
        "split": {"test_size": test_size, "n_train": len(train), "n_test": len(test)},
        "class_counts": {"correct": labels.count(0), "wrong": labels.count(1)},
        "variance_mean": {
            "correct": round(float(np.mean(neg)), 4) if neg else None,
            "wrong": round(float(np.mean(pos)), 4) if pos else None,
        },
        "auc_train": round(_auc(train), 4) if _auc(train) is not None else None,
        "auc_test": round(auc_test, 4) if auc_test is not None else None,
        "auc_test_ci95": auc_ci,
        "theta_youden": round(youden_theta, 3) if youden_theta is not None else None,
        "theta_maxf1": round(f1_theta, 3) if f1_theta is not None else None,
        # All operating-point metrics are evaluated on the held-out TEST split.
        "test_metrics_at_maxf1": _metrics_at(test, chosen) if chosen is not None else None,
        "test_metrics_at_youden": _metrics_at(test, youden_theta) if youden_theta is not None else None,
        "test_metrics_at_0.35": _metrics_at(test, 0.35) if test else None,
        "test_f1_ci95_at_maxf1": f1_ci,
        "train_sweep": [{"theta": t, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}
                        for t, p, r, f1 in rows],
        "per_example": [{"label": l, "variance": v} for l, v in labeled],
    }


def print_report(rep):
    print("\n" + "=" * 72)
    print("TIER 3 θ RECALIBRATION — TriviaQA (variance vs model correctness)")
    print("=" * 72)
    sp = rep["split"]
    print(f"scored {rep['n_scored']}/{rep['n_total']} "
          f"(Tier 3 coverage {rep['tier3_coverage']*100:.0f}%) | "
          f"classes {rep['class_counts']} | train={sp['n_train']} test={sp['n_test']}")
    vm = rep["variance_mean"]
    print(f"mean variance — correct={vm['correct']}  wrong={vm['wrong']}")
    print(f"AUROC: train={rep['auc_train']}  test={rep['auc_test']}  (test 95% CI {rep['auc_test_ci95']})")
    print(f"θ tuned on train — Youden's J = {rep['theta_youden']}   max-F1 = {rep['theta_maxf1']}")
    print("operating-point metrics (evaluated on held-out TEST split):")
    for key in ("test_metrics_at_maxf1", "test_metrics_at_youden", "test_metrics_at_0.35"):
        m = rep[key]
        if m:
            print(f"  {key:>24}: θ={m['theta']}  P={m['precision']}  R={m['recall']}  F1={m['f1']}")
    print(f"test F1 95% CI at max-F1 θ: {rep['test_f1_ci95_at_maxf1']}")
    if rep["auc_test"] is None:
        print("\n⚠ AUROC undefined — only one class present (model got all right or all wrong). "
              "Increase --n.")
    elif rep["auc_test"] < 0.70:
        print("\n⚠ test AUROC < 0.70 — STOP RULE TRIGGERED. Variance does not reliably predict "
              "model errors on this dataset. Do not chase another dataset; write the honest "
              "limitation (narrow high-precision fabrication check) and reframe accordingly.")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="number of questions to sample")
    ap.add_argument("--smoke", action="store_true", help="quick 50-question sanity gate")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--out", default="eval_recalibration_results.json")
    args = ap.parse_args()

    n = 50 if args.smoke else args.n
    items = load_questions(n, args.seed)
    print(f"Loaded {len(items)} questions from {DATASET_ID}/{DATASET_CONFIG}")
    print(f"Model={args.model} provider={args.provider} concurrency={args.concurrency}")
    print(f"Est. ~{len(items)*4} LLM calls (1 answer + paraphrase-gen + 2 responses per item)\n")

    scores = await collect(items, args.model, args.provider, args.concurrency)
    rep = analyze(scores, args.n_boot, args.seed)
    print_report(rep)

    with open(args.out, "w") as f:
        json.dump(rep, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
