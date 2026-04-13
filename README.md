# Aegis — Agentic LLM Gateway & Causal Hallucination Firewall

> Cost-aware multi-model routing with causal intervention-based hallucination detection

Aegis is a production LLM gateway that routes every prompt to the cheapest capable model, detects hallucinations without requiring ground truth, and surfaces every architectural decision in a live dashboard.

---

## Problem Statement

Organizations using LLMs in production face two compounding problems:

1. **Cost waste** — Simple queries hit GPT-4o at $2.50/1M tokens when Llama 3.1 (free) or Gemini Flash ($0.075/1M) would answer just as well.
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

### Request Pipeline

```
Incoming Prompt
      |
[1] Security Gate
      |  — PII scan (email, SSN, phone regex)
      |  — Injection detection ("ignore previous instructions", "jailbreak", ...)
      |  — Domain hard gate: legal/medical/financial → force GPT-4o, no override
      |
[2] Semantic Cache (cosine similarity ≥ 0.85 → return cached, $0.00)
      |  cache miss ↓
[3] Complexity Classifier → Route to cheapest capable model
      |
[4] LLM Call (unified async client, 3-retry with exponential backoff)
      |  fallback to gpt-4o-mini if primary provider unavailable
      |
[3.5] Causal Risk Check
      |  — Tier 1: Hedging phrase scan [FREE, all providers, all requests]
      |  — Tier 3: Paraphrase variance vs θ=0.35
      |             [gated: legal/medical/financial OR complexity > 0.7]
      |
[5] Log to SQLite (cost, model, latency, risk_level, cache_hit, domain)
      |
Response + causal_analysis { is_hallucination, confidence, explanation, pathway }
```

### Offline DoWhy Calibration (runs once, not in request path)

```
1,000 synthetic (prompt, context, response) tuples
      |
Claude Haiku scores response quality (different model family = non-circular judge)
      |
DoWhy: context_relevance → response_quality (+ confounders: length, domain, temperature)
      |
Refutation tests: placebo_treatment, random_common_cause
      |
θ = 0.35  ← causally-justified variance threshold used at runtime
```

---

## Model Pool

| Score Range | Model | Cost per 1M Tokens | Use Case |
|-------------|-------|--------------------|----------|
| 0.00–0.20 | Llama 3.1 8B (Groq / local Ollama) | $0.00 | Simple factual, conversational |
| 0.20–0.35 | Gemini 1.5 Flash | $0.075 | Low-medium complexity |
| 0.35–0.50 | GPT-4o-mini | $0.150 | Medium complexity |
| 0.50–0.70 | Claude 3.5 Haiku | $0.250 | Medium-high, nuanced reasoning |
| 0.70–1.00 | GPT-4o | $2.500 | Complex reasoning, high-stakes domains |

Routing is automatic — the complexity classifier scores each prompt (0.0–1.0) and routes to the cheapest model capable of handling it. Legal, medical, and financial queries are always hard-routed to GPT-4o regardless of complexity score.

If the primary provider is unavailable (e.g. Ollama not running), requests automatically fall back to GPT-4o-mini.

---

## Dashboard

Live stats updated after every request:

- Cumulative cost savings vs. GPT-4o-only baseline
- Model distribution across routing tiers
- Semantic cache hit rate
- Risk flags (MEDIUM + HIGH risk responses, including hallucination detections)
- Average latency (cache hits excluded)

Dashboard pre-seeded with 50 realistic demo requests on first startup — real data is visible immediately before any prompts are sent.

---

## Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- OpenAI API key (required — GPT-4o-mini + GPT-4o)
- Anthropic API key (Claude 3.5 Haiku)
- Google API key (Gemini Flash)
- Ollama with `llama3.1` pulled locally (optional — falls back to GPT-4o-mini automatically)

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

### Running Tests
```bash
cd backend
pytest tests/ -v
# 53 tests, ~8s, no real API calls made
```

---

## Technical Details

### Complexity Classifier

4-factor weighted score:

```python
score = (
    0.20 * vocab_richness(prompt)          +  # type-token ratio + avg word length
    0.20 * structure_score(words, sents)   +  # length and sentence count
    0.35 * question_type_score(verbs)      +  # factual vs analytical vs design (exclusive tiers)
    0.25 * domain_similarity                  # cosine sim to legal/medical/financial/technical prototypes
)

routing_table = {
    (0.00, 0.20): "llama-3.1-8b-instant",  # free, local (Groq or Ollama)
    (0.20, 0.35): "gemini-1.5-flash",
    (0.35, 0.50): "gpt-4o-mini",
    (0.50, 0.70): "claude-3-5-haiku-20241022",
    (0.70, 1.00): "gpt-4o",
}
```

Question type tiers are mutually exclusive — the highest matching tier wins (complex > analytical > factual). Routing confidence is computed from distance to the nearest tier boundary: scores near boundaries return lower confidence than scores deep in a band.

### Semantic Cache

In-memory cache using `sentence-transformers/all-MiniLM-L6-v2`. Threshold 0.85 (not 0.95 — that gives <1% hit rate in practice). Cache hit returns in ~5ms at $0.00. Resets on server restart (intentional for demo).

The same embedder instance is shared between the cache and hallucination detector to avoid loading the model twice (~90MB).

### Security Layer

Three-gate check before any routing:
1. PII regex — blocks email, SSN (`XXX-XX-XXXX`), phone patterns
2. Injection detection — keyword list: `"ignore previous instructions"`, `"jailbreak"`, `"system:"`, etc.
3. Domain hard gate — `legal | medical | financial` → force GPT-4o. This bypass cannot be overridden by the classifier.

### Hallucination Detector (Tier 1 + Tier 3)

**Tier 1 — Hedging phrase detection (free, runs on all responses)**

Scans response for confidence-undermining phrases: `"I'm not sure"`, `"I believe"`, `"might be"`, `"as of my knowledge cutoff"`, etc. Three or more hits → flagged as potential hallucination (MEDIUM risk).

**Tier 3 — Paraphrase variance (gated)**

Only runs if `domain in (legal, medical, financial)` OR `complexity_score > 0.6` OR prompt contains factual question patterns (`"what did"`, `"when did"`, `"who said"`, etc.):

```python
paraphrases = generate(prompt, via="gpt-4o-mini", n=2, temperature=0.7)  # ~$0.00002
r1, r2 = await asyncio.gather(query(p1, model, temp=0), query(p2, model, temp=0))

# Only paraphrase responses compared — both at temperature=0 for a clean causal signal.
# The original response (generated at temp=0.7) is excluded to avoid mixing
# stochastic and deterministic outputs.
variance = 1 - cosine_similarity(embed(r1), embed(r2))

if variance > 0.35:   # θ calibrated offline via DoWhy
    return HIGH_RISK  # pathway="paraphrase_variance"
```

Tier 3 failures (API errors, insufficient paraphrases) degrade gracefully to Tier 1 result.

**Risk level merging:**
- Domain risk: legal/medical → HIGH, financial → MEDIUM, else SAFE
- Detection risk: paraphrase_variance → HIGH, hedging → MEDIUM
- Final risk = max(domain_risk, detection_risk)

**What's intentionally not included:**
Cross-model consensus (Tier 2) was dropped — it doubles latency and cost, and is not demonstrable in real time. The offline DoWhy calibration makes Tier 3 alone defensible.

### Offline DoWhy Calibration

See `notebooks/causal_benchmark.ipynb` for the full calibration. The key claim:

> θ = 0.35 is not a tuned hyperparameter — it is the causally-estimated boundary between context-anchored and context-unanchored responses, validated by placebo treatment refutation.

---

## Project Structure

```
aegis-project/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py                   # /api/chat and /api/stats
│   │   ├── agents/
│   │   │   └── router.py                   # LangGraph 4-node routing agent
│   │   ├── models/
│   │   │   └── schemas.py                  # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── llm_client.py               # Unified async client (5 providers)
│   │   │   ├── classifier.py               # 4-factor complexity scorer
│   │   │   ├── security.py                 # PII + injection + domain gate
│   │   │   ├── domain_classifier.py        # legal/medical/financial detection
│   │   │   ├── embedder.py                 # Shared all-MiniLM-L6-v2 singleton
│   │   │   ├── cache.py                    # In-memory semantic cache (cosine ≥ 0.85)
│   │   │   └── hallucination_detector.py   # Tier 1 hedging + Tier 3 paraphrase variance
│   │   ├── db.py                           # SQLite async wrapper
│   │   └── seed_data.py                    # 50 demo records on first startup
│   ├── tests/
│   │   ├── conftest.py                     # Isolated DB fixture, mocked seeding
│   │   ├── test_security.py                # 11 tests
│   │   ├── test_classifier.py              # 12 tests
│   │   ├── test_cache.py                   # 6 tests
│   │   ├── test_hallucination.py           # 12 tests
│   │   └── test_routes.py                  # 12 tests — 53 total, ~8s
│   ├── main.py
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx                         # State + fetch logic only (~97 lines)
│       ├── types.ts                        # Shared TypeScript interfaces
│       └── components/
│           ├── PromptInput.tsx             # Textarea, demo buttons, submit
│           ├── ResponseCard.tsx            # Response text, routing info, causal analysis card
│           └── Dashboard.tsx              # Stats grid, model distribution, How It Works
├── notebooks/
│   └── causal_benchmark.ipynb             # DoWhy offline calibration + Pearl Ladder benchmark
└── README.md
```

---

## Deployment

| Component | Platform |
|-----------|----------|
| Backend (FastAPI + SQLite) | Railway |
| Frontend (React + Vite) | Vercel |

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
