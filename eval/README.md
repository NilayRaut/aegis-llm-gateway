# Eval

Two scripts back the hallucination-detection claims in the main README. Each
one writes a timestamped JSON file to `eval/results/`. Commit that file
alongside any number you quote from it.

| Script | Output |
|---|---|
| `backend/eval_tier3.py` | `eval/results/tier3_<UTC timestamp>.json` |
| `backend/eval_recalibration.py` | `eval/results/recalibration_<UTC timestamp>.json` |

Every output file starts with a `header` block containing:
- the git commit hash, branch, and a dirty flag for the working tree
- the UTC start and finish times
- the embedding model and the paraphrase model
- the production θ and the θ sweep
- the routed model and provider for each prompt or item

The body holds the per-item results and the metrics, which are computed in
code with TP/FP/FN/TN.

**Both scripts make real, billed LLM API calls.** The call counts below are
estimates taken from the code paths. They do not include retries:
`llm_client` retries up to 3 times, and a non-OpenAI provider that fails
falls back to gpt-4o-mini.

## Setup

```bash
cd backend
pip install -r requirements.txt
pip install scikit-learn "datasets>=2.0.0"   # eval-only deps, not in requirements.txt
cp .env.example .env                         # add OPENAI / ANTHROPIC / GOOGLE / GROQ keys
```

## 1. Tier 3 pilot: `eval_tier3.py`

There are 40 prompts:
- 30 labeled: 15 factual and 15 hallucination-prone (fabricated premise)
- 10 unlabeled borderline prompts, which are recorded but excluded from every
  metric

The script sends each prompt through the full `/api/chat` pipeline of a
running backend, so routing, domain gating, and Tier 1/Tier 3 all behave as
they do in production.

```bash
# terminal 1: start a fresh backend, so the semantic cache is empty
cd backend
uvicorn main:app

# terminal 2
cd backend
python eval_tier3.py
```

Estimated API calls per prompt:

| Step | Calls |
|---|---|
| Domain classification (Groq `llama-3.1-8b-instant`) | 1 |
| Complexity scoring (Groq `llama-3.1-8b-instant`) | 1 |
| Routed model answer | 1 |
| Tier 3, only when gated in: 1 paraphrase generation (gpt-4o-mini) + 2 paraphrase answers (routed model) | 3 |

That is 3 to 6 calls per prompt, so **about 120 to 240 calls for 40
prompts**. The upper bound applies when Tier 3 runs on every prompt. If
`GROQ_API_KEY` is unset, the two Groq calls fall back to local heuristics and
the range becomes about 40 to 160.

The JSON contains:
- **Tier-3-only** P/R/F1: computed on labeled prompts where Tier 3 returned a
  variance score. A prompt is flagged when variance > θ.
- **Combined (Tier 1 + Tier 3)** P/R/F1: computed on all labeled prompts that
  returned a response. A prompt is flagged when the Tier 1 hedging flag fires
  OR variance > θ. The Tier 1 flag is recomputed locally from the response
  text and makes no API call.
- The server's own `is_hallucination` decision.
- A list of prompts where the local reconstruction disagrees with the server.

Each P/R/F1 block also includes TP/FP/FN/TN for every θ in the sweep.

## 2. θ recalibration study: `eval_recalibration.py`

This study uses TriviaQA `rc.nocontext` (validation split) and labels each
item by whether the model's own answer is correct. It reports AUROC of
variance against those errors on a held-out stratified test split, with
`--seed 42` and `test_size 0.4`. It calls the model directly and does not go
through the router.

```bash
cd backend
python eval_recalibration.py --smoke     # 50 questions
python eval_recalibration.py --n 400     # full study
```

Estimated API calls per question: 1 answer, 1 paraphrase generation, and 2
paraphrase answers. All use `--model`/`--provider`, which defaults to
gpt-4o-mini/openai, so each question costs 4 calls:

| Run | Calls |
|---|---|
| `--smoke` | about 200 |
| `--n 400` | about 1,600 |

The TriviaQA download from the Hugging Face Hub is not an LLM call.

The JSON records:
- the dataset split size and the number of questions sampled, answered, and
  scored
- the train/test split sizes and class counts for each split
- the per-item answer, correctness, variance, and split assignment
- train and held-out-test AUROC, with a bootstrap 95% CI for the test AUROC
- test-split P/R/F1 with TP/FP/FN/TN at three θ values: the max-F1 θ chosen
  on train, Youden's J θ, and the production θ
