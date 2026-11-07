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

Output
------
Per-item results (question, model answer, correctness label, variance score,
tier3_ran, train/test split, routed model/provider) and the held-out AUROC are
written to eval/results/recalibration_<UTC timestamp>.json with a provenance
header (git commit, date, embedding model, θ sweep). The report also records
the source dataset size and the number of items sampled / scored / in each
split.

Run (spends API budget — ~4 cheap LLM calls per question; see eval/README.md):
    cd backend
    pip install "datasets>=2.0.0"
    python eval_recalibration.py --smoke         # 50 questions, sanity gate
    python eval_recalibration.py --n 400         # full study
"""

import argparse
import asyncio
import random
import re
import string
import sys

import numpy as np
from dotenv import load_dotenv

# Load provider keys before importing the client (it reads env at init).
load_dotenv()

from sklearn.metrics import roc_auc_score, roc_curve, precision_recall_fscore_support

from app.services.embedder import EMBEDDING_MODEL
from app.services.hallucination_detector import PARAPHRASE_MODEL, THETA, hallucination_detector
from app.services.llm_client import llm_client
from eval_common import confusion_metrics, git_info, utc_now, write_results

DATASET_ID = "mandarjoshi/trivia_qa"
DATASET_CONFIG = "rc.nocontext"
DATASET_SPLIT = "validation"
THETA_SWEEP = [round(t, 3) for t in np.linspace(0.05, 0.70, 66)]

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


def load_questions(n: int, seed: int) -> tuple[list[tuple[str, list[str]]], int]:
    """
    Return (items, dataset_size): n random (question, normalized_aliases) pairs
    from TriviaQA rc.nocontext, plus the size of the split they were drawn from.
    """
    from datasets import load_dataset

    ds = load_dataset(DATASET_ID, DATASET_CONFIG, split=DATASET_SPLIT)
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    out = []
    for i in idx[:n]:
        row = ds[i]
        aliases = row["answer"].get("normalized_aliases") or [row["answer"].get("normalized_value", "")]
        out.append((row["question"], [a for a in aliases if a]))
    return out, len(ds)


async def score_item(question, aliases, model, provider, sem):
    """
    Returns a per-item result dict.
      label = 1 (wrong/hallucination) | 0 (correct) | None (answer call failed)
    Gets the model's answer to the original question, grades it, then runs Tier 3.
    """
    item = {
        "question": question,
        "aliases": aliases,
        "model": model,
        "provider": provider,
        "answer": None,
        "correct": None,
        "label": None,
        "variance_score": None,
        "tier3_ran": False,
        "split": None,
        "error": None,
    }
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
            item["error"] = f"{type(exc).__name__}: {exc}"
            return item

        correct = is_correct(answer_text, aliases)
        result = await hallucination_detector.tier3_paraphrase_variance(
            original_prompt=question, original_response="",
            model=model, provider=provider, llm_client=llm_client,
        )
    item.update({
        "answer": answer_text,
        "correct": correct,
        "label": 0 if correct else 1,
        "variance_score": result.variance_score,
        "tier3_ran": result.variance_score is not None,
    })
    return item


async def collect(items, model, provider, concurrency):
    sem = asyncio.Semaphore(concurrency)
    tasks = [score_item(q, aliases, model, provider, sem) for q, aliases in items]
    results = await asyncio.gather(*tasks)
    answered = [r for r in results if r["label"] is not None]
    for done, r in enumerate(results, 1):
        if r["label"] is None:
            continue
        tag = "OK  " if r["label"] == 0 else "WRONG"
        vs = r["variance_score"]
        vs_str = f"{vs:.4f}" if vs is not None else "None "
        print(f"[{done:>3}/{len(items)}] [{tag}] var={vs_str}  {r['question'][:60]}")
    n_correct = sum(1 for r in answered if r["correct"])
    acc = n_correct / len(answered) if answered else 0.0
    print(f"\nmodel accuracy: {n_correct}/{len(answered)} = {acc*100:.0f}%  "
          f"(wrong/hallucination class = {len(answered)-n_correct})")
    return results


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
    return {"theta": round(t, 3), **confusion_metrics(labels, preds)}


def stratified_split(labeled, test_size, seed):
    """Class-stratified train/test split so both classes appear in each side."""
    rng = random.Random(seed)
    by_label = {0: [], 1: []}
    for item in labeled:
        by_label[item["label"]].append(item)
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


def analyze(results, n_boot, seed, test_size=0.4):
    """
    Choose θ on the TRAIN split (max-F1 and Youden's J); report AUROC/F1 + CIs
    on the held-out TEST split. AUROC is threshold-free, so its test value is
    the headline generalization number; θ is tuned only on train to avoid the
    in-sample optimism of picking and reporting a threshold on the same data.
    """
    answered = [r for r in results if r["label"] is not None]
    scored_items = [r for r in answered if r["variance_score"] is not None]
    coverage = len(scored_items) / len(answered) if answered else 0.0

    train_items, test_items = stratified_split(scored_items, test_size, seed)
    for r in train_items:
        r["split"] = "train"
    for r in test_items:
        r["split"] = "test"

    labeled = [(r["label"], r["variance_score"]) for r in scored_items]
    train = [(r["label"], r["variance_score"]) for r in train_items]
    test = [(r["label"], r["variance_score"]) for r in test_items]
    labels = [l for l, _ in labeled]
    pos = [v for l, v in labeled if l == 1]
    neg = [v for l, v in labeled if l == 0]

    # θ candidates chosen on TRAIN only
    rows = []
    best_f1, f1_theta = -1.0, None
    for t in THETA_SWEEP:
        m = _metrics_at(train, t)
        rows.append(m)
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
        "n_total": len(results),
        "n_answered": len(answered),
        "n_answer_errors": len(results) - len(answered),
        "n_scored": len(labeled),
        "tier3_coverage": round(coverage, 3),
        "split": {
            "test_size": test_size, "seed": seed, "stratified": True,
            "n_train": len(train), "n_test": len(test),
            "train_class_counts": {"correct": [l for l, _ in train].count(0),
                                   "wrong": [l for l, _ in train].count(1)},
            "test_class_counts": {"correct": [l for l, _ in test].count(0),
                                  "wrong": [l for l, _ in test].count(1)},
        },
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
        f"test_metrics_at_{THETA}": _metrics_at(test, THETA) if test else None,
        "test_f1_ci95_at_maxf1": f1_ci,
        "train_sweep": rows,
    }


def print_report(rep):
    print("\n" + "=" * 72)
    print("TIER 3 θ RECALIBRATION — TriviaQA (variance vs model correctness)")
    print("=" * 72)
    sp = rep["split"]
    print(f"scored {rep['n_scored']}/{rep['n_total']} (answered {rep['n_answered']}) "
          f"(Tier 3 coverage {rep['tier3_coverage']*100:.0f}%) | "
          f"classes {rep['class_counts']} | train={sp['n_train']} test={sp['n_test']}")
    vm = rep["variance_mean"]
    print(f"mean variance — correct={vm['correct']}  wrong={vm['wrong']}")
    print(f"AUROC: train={rep['auc_train']}  test={rep['auc_test']}  (test 95% CI {rep['auc_test_ci95']})")
    print(f"θ tuned on train — Youden's J = {rep['theta_youden']}   max-F1 = {rep['theta_maxf1']}")
    print("operating-point metrics (evaluated on held-out TEST split):")
    for key in ("test_metrics_at_maxf1", "test_metrics_at_youden", f"test_metrics_at_{THETA}"):
        m = rep[key]
        if m:
            print(f"  {key:>24}: θ={m['theta']}  P={m['precision']}  R={m['recall']}  F1={m['f1']}  "
                  f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}")
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
    args = ap.parse_args()

    started_at = utc_now()
    n = 50 if args.smoke else args.n
    items, dataset_size = load_questions(n, args.seed)
    print(f"Loaded {len(items)} of {dataset_size} questions from "
          f"{DATASET_ID}/{DATASET_CONFIG} ({DATASET_SPLIT} split)")
    print(f"Model={args.model} provider={args.provider} concurrency={args.concurrency}")
    print(f"Est. ~{len(items)*4} LLM calls (1 answer + paraphrase-gen + 2 responses per item)\n")

    results = await collect(items, args.model, args.provider, args.concurrency)
    rep = analyze(results, args.n_boot, args.seed)
    print_report(rep)

    header = {
        "study": "tier3_recalibration",
        "script": "backend/eval_recalibration.py",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": utc_now().isoformat(),
        "git": git_info(),
        "args": vars(args),
        "dataset": {
            "id": DATASET_ID,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "split_size": dataset_size,
            "n_sampled": len(items),
        },
        "embedding_model": EMBEDDING_MODEL,
        "paraphrase_model": PARAPHRASE_MODEL,
        "production_theta": THETA,
        "theta_sweep": THETA_SWEEP,
        # This study calls the model directly (no router), so every item uses
        # the same --model/--provider; recorded per item for parity with eval_tier3.
        "routed_model_per_item": [
            {"question": r["question"], "model": r["model"], "provider": r["provider"]}
            for r in results
        ],
    }
    path = write_results("recalibration", started_at, {
        "header": header,
        "report": rep,
        "results": results,
    })
    print(f"\nWrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
