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
      |  cache miss
[3] Complexity Classifier → Route to cheapest capable model
      |
[4] LLM Call (unified async client, 3-retry with backoff)
      |
[5] Causal Risk Check
      |  — Tier 1: Hedging phrase scan [FREE] — all providers
      |  — Tier 3: Paraphrase variance vs θ=0.35 [gated: legal/medical/financial or complexity > 0.7]
      |
[6] Log to SQLite (cost, model, latency, risk_level, cache_hit, domain)
      |
Response + causal_analysis { is_hallucination, confidence, explanation }
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

| Tier | Model | Cost per 1M Tokens | Use Case |
|------|-------|--------------------|----------|
| Free | Llama-3 8B (local, Ollama) | $0.00 | Simple factual, conversational |
| Budget | Gemini 1.5 Flash | $0.075 | Low-medium complexity |
| Standard | GPT-4o-mini | $0.150 | Medium complexity |
| Quality | Claude 3.5 Haiku | $0.250 | Medium-high, nuanced reasoning |
| Premium | GPT-4o | $2.500 | Complex reasoning, high-stakes domains |

Routing is automatic — the complexity classifier scores each prompt (0.0–1.0) and routes to the cheapest model capable of handling it. Legal, medical, and financial queries are always hard-routed to GPT-4o regardless of complexity score.

---

## Dashboard

Live stats updated after every request:

- Cumulative cost savings vs. GPT-4o-only baseline
- Model distribution across routing tiers
- Semantic cache hit rate
- Risk flags (MEDIUM + HIGH risk responses)
- Average latency (cache hits excluded)

Dashboard pre-seeded with 50 realistic demo requests on first startup — real data is visible immediately before any prompts are sent.

---

## Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- OpenAI API key (required — GPT-4o-mini + GPT-4o)
- Anthropic API key (Claude 3.5 Haiku)
- Google API key (Gemini Flash)
- Ollama with `llama3:8b` pulled locally (optional — falls back to GPT-4o-mini)

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

## Technical Details

### Complexity Classifier

4-factor weighted score:

```python
score = (
    0.30 * semantic_norm(embedding_distance_from_simple_cluster) +
    0.25 * structure_score(token_count, sentence_count) +
    0.25 * question_type_score(reasoning_verbs, multi_part) +
    0.20 * domain_keyword_density
)

routing_table = {
    (0.0, 0.2): "llama-3",
    (0.2, 0.4): "gemini-1.5-flash",
    (0.4, 0.6): "gpt-4o-mini",
    (0.6, 0.8): "claude-haiku",
    (0.8, 1.0): "gpt-4o",
}
```

### Semantic Cache

In-memory cache using `sentence-transformers/all-MiniLM-L6-v2`. Threshold 0.85 (not 0.95 — that gives <1% hit rate in practice). Cache hit returns in ~5ms at $0.00.

### Security Layer

Three-gate check before any routing:
1. PII regex — blocks email, SSN (`XXX-XX-XXXX`), phone patterns
2. Injection detection — keyword list: `"ignore previous instructions"`, `"jailbreak"`, `"system:"`, etc.
3. Domain hard gate — `legal | medical | financial` → force GPT-4o. This bypass cannot be overridden by the classifier.

### Hallucination Detector (Tier 1 + Tier 3)

**Tier 1 — Hedging phrase detection (free, runs on all responses)**  
Scans response for confidence-undermining phrases: `"I'm not sure"`, `"I believe"`, `"you should consult a professional"`, `"as of my knowledge cutoff"`, etc. → MEDIUM risk if found.

**Tier 3 — Paraphrase variance (gated)**  
Only runs if domain = legal/medical/financial OR complexity_score > 0.7:
```python
paraphrase = rephrase(prompt, via="gpt-4o-mini")   # ~$0.000015
r1 = query(original_prompt, model=selected_model)
r2 = query(paraphrase, model=selected_model)
variance = 1 - cosine_similarity(embed(r1), embed(r2))

if variance > 0.35:   # θ calibrated offline via DoWhy
    return HIGH_RISK
```

**What's intentionally not included:**  
Cross-model consensus (Tier 2) was dropped — it doubles latency and cost, and is not demonstrable in real time. The offline DoWhy calibration makes Tier 3 alone defensible.

### Offline DoWhy Calibration

See `notebooks/` for the full calibration. The key claim:

> θ = 0.35 is not a tuned hyperparameter — it is the causally-estimated boundary between context-anchored and context-unanchored responses, validated by placebo treatment refutation.

---

## Project Structure

```
aegis-project/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py               # /api/chat and /api/stats endpoints
│   │   ├── agents/
│   │   │   └── router.py               # LangGraph routing agent (classify→route→call→return)
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── llm_client.py           # Unified async client (OpenAI, Anthropic, Google, Ollama)
│   │   │   ├── classifier.py           # 4-factor complexity scorer
│   │   │   ├── security.py             # PII + injection detection + domain gate
│   │   │   ├── domain_classifier.py    # legal/medical/financial/general detection
│   │   │   ├── cache.py                # In-memory semantic cache (cosine ≥ 0.85)
│   │   │   └── hallucination_detector.py  # Tier 1 hedging + Tier 3 paraphrase variance
│   │   ├── db.py                       # SQLite async wrapper (log_request, get_stats)
│   │   └── seed_data.py                # 50 demo records seeded on first startup
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx                     # Main UI (prompt input, response card, dashboard)
│       └── components/                 # (componentization — Phase 5)
├── notebooks/
│   └── pearl_ladder/                   # DoWhy offline calibration + Pearl Ladder benchmark
├── data/
│   └── synthetic/                      # 1,000 calibration tuples
└── README.md
```

---

## Deployment

| Component | Platform |
|-----------|----------|
| Backend (FastAPI + SQLite) | Railway |
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
