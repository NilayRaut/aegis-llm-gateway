# Aegis — Agentic LLM Gateway & Causal Hallucination Firewall

> Cost-aware multi-model routing with causal intervention-based hallucination detection

Aegis is a production LLM gateway that routes every prompt to the cheapest capable model, detects hallucinations without requiring ground truth, and surfaces every architectural decision in a live dashboard.

---

## Problem Statement

Organizations using LLMs in production face two compounding problems:

1. **Cost waste** — Simple queries hit GPT-4o at $2.50/1M tokens when Llama-3 (free) or Gemini Flash ($0.075/1M) would answer just as well.
2. **Silent hallucinations** — LLMs produce confident, fluent, incorrect answers. In medical, legal, or financial contexts, this causes real harm. The core difficulty: in production, there is no ground truth to check against.

Aegis addresses both problems. The hallucination problem is solved causally, not through fact-checking.

---

## Differentiation

OpenRouter, LiteLLM, and AWS Bedrock Converse solve the routing problem. By 2026 that is commoditized.

What Aegis adds that no commercial router does:

**Causal hallucination detection without ground truth.**

Instead of asking "is this response correct?" — which requires ground truth — Aegis asks:

> *Does the factual claim change when only the phrasing changes?*

If a model's claim shifts when the question is paraphrased, that is a causal signal: the claim was not anchored to knowledge, only to surface prompt features. This is a `do(X)` intervention in causal language. It requires no labels, no ground truth, and no external knowledge base.

The variance threshold (θ = 0.35) that separates stable facts from hallucination-prone claims is calibrated offline using DoWhy, with placebo treatment refutation tests to confirm the threshold is causally justified — not statistically tuned.

---

## System Architecture

### Two Subsystems

```
OFFLINE (runs once, on synthetic data)
---------------------------------------
1,000 synthetic (prompt, context, response) tuples
      |
Claude Haiku scores quality (different family = non-circular judge)
      |
DoWhy: context_relevance → response_quality (+ confounders)
      |
Refutation tests: placebo_treatment, random_common_cause
      |
theta = 0.35  <-- calibrated variance threshold
      |
      | validates threshold for
      v

ONLINE (every request)
---------------------------------------
Incoming Prompt
      |
Semantic Cache Check (cosine similarity >= 0.95 → return cached)
      |  cache miss
Complexity Classifier → Route to optimal model
      |
Tiered Hallucination Detector:
  |
  Tier 1: Logprob check [FREE] ──────────── ~60% exit SAFE
  |
  Tier 2: Cross-model consensus [$0.0003] ── ~30% exit
  |
  Tier 3: Causal intervention [$0.0006] ───── ~10% only
           do(phrasing=X): paraphrase 3x
           measure claim variance vs theta = 0.35
           Domain gate: legal/medical/financial → always Tier 3
      |
Response + Risk Level (SAFE / MEDIUM_RISK / HIGH_RISK)
```

### Detection Cost Per 1,000 Queries

| Tier | Query Share | Cost |
|------|-------------|------|
| Tier 1 | 60% (600) | $0.00 |
| Tier 2 | 30% (300) | $0.09 |
| Tier 3 | 10% (100) | $0.06 |
| **Total** | 1,000 | **$0.15** |

Always running Tier 3 would cost $0.60 per 1,000 queries. The tiered approach delivers a 75% reduction in detection cost.

---

## Model Pool

| Tier | Model | Cost per 1M Tokens | Use Case |
|------|-------|--------------------|----------|
| Free | Llama-3 8B (local, Ollama) | $0.00 | Simple factual, conversational |
| Budget | Gemini 1.5 Flash | $0.075 | Low-medium complexity |
| Standard | GPT-4o-mini | $0.150 | Medium complexity |
| Quality | Claude 3 Haiku | $0.250 | Medium-high, nuanced reasoning |
| Premium | GPT-4o | $2.500 | Complex reasoning only |

Routing is automatic — the complexity classifier scores each prompt and routes to the cheapest model capable of handling it.

---

## Dashboard Metrics

- Cumulative cost savings vs. GPT-4o-only baseline
- Model distribution across routing tiers
- Semantic cache hit rate with ROI
- Hallucination risk breakdown per session (SAFE / MEDIUM / HIGH)
- Average latency per model tier

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API key
- Anthropic API key (Claude)
- Google API key (Gemini)
- Ollama with `llama3:8b` pulled locally

### Backend
```bash
conda activate neu_work
cd backend
pip install -r requirements.txt
cp .env.example .env
# Add API keys to .env
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Endpoints
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Technical Approach

### Complexity Classification
```python
# Features: embedding distance from "simple" cluster,
# token count, named entity density, reasoning verb presence
complexity_score = classifier.score(prompt)  # float: 0.0 to 1.0

routing_table = {
    (0.0, 0.2): "llama-3",
    (0.2, 0.4): "gemini-flash",
    (0.4, 0.6): "gpt-4o-mini",
    (0.6, 0.8): "claude-haiku",
    (0.8, 1.0): "gpt-4o",
}
```

### Causal Intervention Test (Runtime, Tier 3)
```python
# do(phrasing=X): paraphrase and re-query
paraphrases = generate_paraphrases(prompt, n=3)
responses = [query_llm(p, model=selected_model) for p in paraphrases]
claims = [extract_factual_claims(r) for r in responses]
variance = semantic_variance(claims)  # cosine distance on claim embeddings

if variance > THETA:  # THETA = 0.35, calibrated offline by DoWhy
    return HallucinationRisk.HIGH
```

### Offline DoWhy Calibration (Notebook, Not in Request Path)
```python
# Causal DAG — no ground truth required
# Treatment: context_relevance
# Outcome: response_quality (scored by Claude Haiku)
# Confounders: prompt_length, domain, temperature

model = CausalModel(
    data=synthetic_df,
    treatment="context_relevance",
    outcome="response_quality",
    graph=causal_dag
)
estimate = model.estimate_effect(identified_estimand, method_name="backdoor")
refutation = model.refute_estimate(estimate, method_name="placebo_treatment")
# Validates that THETA = 0.35 is causally grounded
```

---

## Project Structure

```
aegis-project/
├── backend/
│   ├── app/
│   │   ├── api/routes.py                    # FastAPI endpoints
│   │   ├── agents/router.py                 # LangGraph routing agent
│   │   ├── models/schemas.py                # Pydantic models
│   │   └── services/
│   │       ├── llm_client.py                # All LLM API clients
│   │       ├── classifier.py                # Complexity scorer
│   │       ├── cache.py                     # Semantic cache
│   │       ├── hallucination_detector.py    # Tiered causal detector
│   │       └── domain_classifier.py         # High-stakes domain detection
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx
│       └── components/
│           ├── Dashboard.tsx
│           └── PromptTester.tsx
├── notebooks/
│   └── causal_calibration.ipynb            # DoWhy offline calibration
├── data/
│   ├── synthetic/                           # 1,000 calibration tuples
│   └── cache/
└── README.md
```

---

## Deployment

| Component | Platform |
|-----------|----------|
| Backend (FastAPI + PostgreSQL) | Railway |
| Frontend (React) | Vercel |

---

## Scope Boundaries

- This is not a fact-checking or retrieval system — no external knowledge base is queried.
- The DoWhy calibration notebook is an offline validation artifact. It does not run in the request path.
- The variance threshold (θ = 0.35) is fixed at runtime from the offline calibration output.
- This system is not a replacement for human review in regulated domains.

---

## License

MIT License

## Course

INFO 7390 — Advances in Data Science, Northeastern University
