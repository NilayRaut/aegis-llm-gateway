# Pilot Set Audit — Tier 3 Threshold (θ = 0.35)

**Scope.** Documentation/audit only. No calibration was re-run, θ was not changed, no detection code was modified, and no external APIs were called. Every number below is either read directly from a file in this repository or computed by plain arithmetic from numbers stated in a repository file (each such case is marked).

**Claim under audit** (README, "Scope Boundaries"): θ = 0.35 is "calibrated on a 30-sample pilot labeled set (15 factual, 15 hallucination-prone): combined detector precision 0.82, recall 0.60, F1 0.69; Tier 3 alone achieves precision 0.67 at θ = 0.35."

**Bottom line.**
- The pilot set's prompts and labels **are** in the repo, hard-coded in `backend/eval_tier3.py`: 30 labeled prompts (15 factual, 15 hallucination-prone) plus 10 unlabeled borderline prompts.
- The **outputs** of that run (variance scores, flags, predictions) are **not** in the repo. The script's output file `backend/eval_results.txt` is gitignored and has never been committed.
- So P/R/F1 at θ = 0.35 **cannot be recomputed from stored predictions**. The only source for 0.82 / 0.60 / 0.69 is the compiled paper PDF, which states the counts.
- No code in the repo computes the "combined" (Tier 1 + Tier 3) metrics. `eval_tier3.py` only computes Tier-3-only metrics.

---

## 1. Candidate files found

I searched every tracked file and the full git history (97 commits, all branches) for θ, `0.35`, `0.82`, precision, recall, F1, pilot, calibration and labeled data.

| Path | What it is | Pilot data? |
|---|---|---|
| `backend/eval_tier3.py` | Tier 3 validation script. Hard-codes the `FACTUAL` (15), `HALLUCINATION_PRONE` (15) and `BORDERLINE` (10) prompt lists, calls the local `/api/chat`, and sweeps θ ∈ {0.10 … 0.50} printing P/R/F1/TP/FP/FN/TN. Added in commit `6e61772` ("30-sample labeled validation study … backing paper Table 3"). | **Yes. Contains the labeled set (prompts + labels only).** |
| `backend/eval_tier3.py` → `eval_results.txt` | The output file the script's docstring says to write (`tee eval_results.txt`). | **Not in repo.** Listed in `.gitignore` (`backend/eval_results.txt`) and absent from all git history. |
| `docs/Aegis__Cost_Aware_Multi_Model_LLM_Routing_with_Causal_Hallucination_Detection.pdf` | Compiled paper. §6.4 and Table 3 report the pilot results with counts. | Reports results and counts. No per-prompt data. |
| `backend/eval_recalibration.py` | Follow-up TriviaQA generalization study. Its docstring says it "Replaces the n=30 pilot in eval_tier3.py". Loads the dataset at runtime. | No. A different study. Its output `backend/eval_recalibration_results.json` is gitignored and not in the repo. |
| `backend/app/services/hallucination_detector.py` | Defines `THETA: float = 0.35`. Docstring says "θ=0.35 empirically determined: factual queries <0.20, hallucination-prone >0.40". | No data. |
| `backend/tests/test_hallucination.py` | Unit tests. Tier 3 tests mock the LLM and embedder to force variance values. | No. Synthetic fixtures for unit tests, not calibration data. |
| `notebooks/data/benchmark_checkpoint.csv`, `notebooks/data/benchmark_results_scored.csv` | 30 rows each. Columns: `model, question_id, rung, rung_name, domain, response_text, score, failure_mode, reasoning, latency_ms, error`. 15 gpt-4o-mini + 15 claude-haiku, 10 each per Pearl rung. | **No.** The row count is also 30, but this is the Pearl-ladder causal-reasoning benchmark. There are no factual/hallucination labels and no variance column. |
| `notebooks/consistency_benchmark.ipynb` | Pearl-ladder causal-reasoning benchmark notebook (produces the CSVs above). It discusses Tier 3 in prose only. | No. |
| `notebooks/causal_benchmark.ipynb` (history only, added `dfd51ca`, later removed) | Earlier notebook. | No matches for pilot/θ/precision. |
| `data/cache/`, `data/synthetic/`, `data/test/`, `notebooks/data/.gitkeep` | Placeholder `.gitkeep` files only. Contents are gitignored. | No. |
| `README.md`, frontend files (`ResponseCard.tsx`, `LandingPage.tsx`, `PromptLibrary.tsx`, `DemoTour.tsx`, `EmptyState.tsx`, `types.ts`) | Display/state θ = 0.35. | No data. |

## 2. The calibration set: `backend/eval_tier3.py`

| Item | Value | Source |
|---|---|---|
| Labeled examples | **30** | `LABELED = [(p, 0) for p in FACTUAL] + [(p, 1) for p in HALLUCINATION_PRONE]` |
| Not-hallucination (label 0) | **15** | `FACTUAL` list |
| Hallucination-prone (label 1) | **15** | `HALLUCINATION_PRONE` list |
| Additional unlabeled prompts | **10** | `BORDERLINE`, label `-1`, excluded from metrics. The comment says "label post-hoc based on ground truth", but no post-hoc labels exist in the repo. |
| Class balance | 50 / 50 | |
| Label field | The integer second element of each `(prompt, label)` tuple: `0` = factual, `1` = hallucination-prone, `-1` = borderline. Each result record has the keys `prompt`, `label`, `variance_score`, `is_hallucination`, `pathway`. | |

**Labeling method (established from the code).** Labels are assigned **by construction**. Each prompt is written into one of two hard-coded lists, and list membership is the label. No annotation step, model-generated labels or per-response judgement exist in the code.
- Factual prompts are questions about well-established facts (e.g. "When did World War II end?", "What did Marie Curie discover?").
- Hallucination-prone prompts all assert a **fabricated premise**: nonexistent researchers or studies, events that never happened, or impossible technology (e.g. "According to the 2024 WHO report on teleportation therapy…").
- The label therefore describes the **prompt** (real vs fabricated premise). It does **not** describe whether the model's response actually hallucinated. A model that correctly answers "no such study exists" still counts as label 1. The paper's §6.4 says the 6 false negatives are exactly these cases.

The paper's description matches the file: "15 factual (well-established scientific and historical facts with definitive answers) and 15 hallucination-prone queries (fabricated researchers, future events, unknowable specifics)".

## 3. Recomputed metrics at θ = 0.35

**Not possible from stored predictions.** No file in the repo, current or historical, contains per-prompt variance scores, `is_hallucination` flags or predictions for the pilot prompts. `eval_results.txt` was never committed. The metrics were **not** recomputed by re-running the study, because that would need live LLM API calls and would amount to re-calibration. Both are out of scope.

**Arithmetic check of the paper's own counts (not a recomputation).** The paper (§6.4, Table 3) states the counts. Checking them by arithmetic only:

| | Combined (Tier 1 + Tier 3), n = 30 | Tier 3 only, θ = 0.35, n = 23 | Tier 3 only, θ = 0.40, n = 23 |
|---|---|---|---|
| TP (stated) | 9 | 4 | 4 |
| FP (stated) | 2 | 2 | 0 |
| FN | 6 (stated in text: "The 6 missed hallucination prompts") | not stated | not stated |
| TN | not stated; 13 is implied by 15 factual − 2 FP | not stated | not stated |
| Precision stated → TP/(TP+FP) | 0.82 → 9/11 = 0.818 ✅ | 0.67 → 4/6 = 0.667 ✅ | 1.00 → 4/4 ✅ |
| Recall stated | 0.60 → 9/15 = 0.600 ✅ | 0.44 | 0.44 |
| F1 stated → 2PR/(P+R) | 0.69 → 0.692 ✅ | 0.53 | 0.62 |

**Verdict:** the reported 0.82 / 0.60 / 0.69 are **arithmetically consistent with the counts stated in the paper**. They are **not verified against data**, because the underlying per-prompt results are not in the repo.

**Further observations from the files:**
1. **No code computes the combined metric.** `eval_tier3.py` records `is_hallucination` for each prompt but computes P/R/F1 only on `variance_score` for prompts where Tier 3 ran. The "Combined (30)" column was produced outside the committed code.
2. **The script never prints the Tier-3 subset size of 23 directly.** It prints `Tier 3 triggered: {n}/30`, so 23 would have come from a run whose output is not stored.
3. **The rationale for θ = 0.35 is inconsistent across sources.** The paper says θ = 0.35 is "intentionally lower to bias toward precision". But Table 3 shows θ = 0.40 has the higher precision (1.00 vs 0.67) at the same recall (0.44). The deleted README wording from commit `47a356e` said θ = 0.35 was chosen "to bias toward higher recall", yet Tier 3 recall is 0.44 at both thresholds. So by the paper's own table, θ = 0.35 is not the max-F1 point (0.40 is), not the higher-precision point, and not a higher-recall point.
4. **The docstring is off.** It says "40 labeled prompts", but only 30 are labeled. The other 10 are unlabeled borderline prompts.
5. **The README number came first.** It was added in commit `47a356e` (2026-04-26 12:24) about 15 minutes before `eval_tier3.py` was committed in `6e61772` (12:39).
6. **The detector has changed since the pilot.** Since `6e61772`, `hallucination_detector.py` has changed only by additions (+87/−1, telemetry for latency and escalation rate). No change to `THETA`, the variance formula or the gating conditions shows up in the diff. Whether the routing models or providers used during the pilot match today's configuration is not recorded.

## 4. Tier distribution (60/30/10) and routing accuracy — report only

**60/30/10 tier distribution.** The string or ratio "60/30/10" (or 60%/30%/10%) **does not appear anywhere** in the current repo or in any commit in its git history. The only tier mixes in the repo are:
- Paper §4.2: "Assuming a realistic workload where 30% of queries are simple (C < 0.45), 50% are medium …, and 20% are complex." This is an explicit **assumption**.
- Paper §10.3 cost model: weights 0.30 / 0.20 / 0.30 / 0.10 / 0.10 across the five tiers, giving "≈ $0.43 per 1M tokens". These are **assumed weights**, not measurements.
- `backend/app/seed_data.py`: a hand-built set of 50 demo records with a fixed model mix (8 llama3.1, 10 gemini-2.5-flash, 12+5 gpt-4o-mini including 5 cache hits, 5 claude-haiku, 10 gpt-4o). This is **synthetic seed data**. The README's 40–60% savings figure is computed on this "50-record synthetic workload".
- `backend/benchmark_vllm.py`: a 10-prompt mix "that mirror[s] Aegis's complexity distribution (2 simple / 4 mid / 3 complex / 1 factual)". This is **chosen by hand**, not measured.
- Runtime telemetry: `/api/stats` `model_distribution` counts the live requests in the SQLite log, and `/api/tier3-overhead` reports `tier3_rate_pct` (the Tier 3 escalation rate). These **measure** the distribution for whatever traffic a deployment sees, but no measured results are stored in the repo.

**Conclusion:** no tier distribution is measured on real traffic anywhere in the repo. Every stated distribution is assumed or synthetic, and 60/30/10 in particular has no source in the repo.

**Routing accuracy.** **Not reported anywhere.**
- No script, test or document compares routed tiers against ground-truth labels for the "correct" tier.
- `classifier._routing_confidence()` returns a heuristic "confidence that the score landed in the correct routing band", computed only from the distance to the nearest band boundary (`min(0.5 + dist·3, 0.95)`). It is not an accuracy measurement.
- `tests/test_classifier.py` asserts the route for a few hand-picked scores and prompts. These are unit tests, not an accuracy evaluation.
- The paper's hypothesis says the classifier can route "with accuracy sufficient to reduce per-request cost by ≥30%", but it reports no accuracy number.
- The only "accuracy" figure in the code is `eval_recalibration.py`'s model *answer* accuracy on TriviaQA. That measures answer correctness, not routing accuracy, and its output is not stored.

## Not determinable from the repo

- **Per-prompt results of the pilot run**: variance scores, `is_hallucination` flags, pathways and predictions. `eval_results.txt` was gitignored and never committed.
- **An independent recomputation of P/R/F1 at θ = 0.35.** The 0.82 / 0.60 / 0.69 figures can only be traced to the paper PDF's stated counts.
- **TN for the combined detector, and FN/TN for the Tier-3-only subset**, as stated values. The paper does not give them (combined TN = 13 is only implied).
- **Which 23 of the 30 labeled prompts triggered Tier 3**, and the class split of that subset.
- **How the "combined" (Tier 1 + Tier 3) metric was computed.** No code in the repo does this.
- **Which routing model(s), providers, embedding model version and date** produced the pilot results. These depend on the live `/api/chat` routing at run time and were not recorded.
- **Whether the run was repeated, and run-to-run variance.** Paraphrases are generated at temperature 0.7, so results are stochastic.
- **Who wrote the prompts and labels, and how.** The code shows labels by list membership, but not whether the lists were hand-written, model-generated, reviewed or double-annotated.
- **Post-hoc labels for the 10 `BORDERLINE` prompts.** The code comment says they would be labeled manually, but no labels exist.
- **The source of the "factual < 0.20, hallucination-prone > 0.40" variance gap** cited in `hallucination_detector.py` and the paper. No stored variance data supports it.
- **The Wilson-score "±0.18" F1 confidence interval** stated in the paper. There is no data or code to reproduce it.
- **Any measured tier distribution, and any source for "60/30/10".**
- **Routing accuracy.**
