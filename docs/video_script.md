# Aegis — Video Narration Script

**Target length:** 10–15 minutes  
**Format:** ElevenLabs voiceover + screen recording  
**Delivery:** Plain prose, no brackets except for screen cues `[CUE: ...]`

---

## Scene 1 — Hook (0:00–1:00)

Picture this: your team ships an AI product. Every single user query — "What's the weather?" or "Design me a distributed database with CQRS and event sourcing" — hits GPT-4o at two dollars and fifty cents per million tokens. Within a week, the bill is terrifying. And somewhere buried in that spend, your model is confidently making things up — citing papers that don't exist, inventing case law, hallucinating treatment protocols — and you have no idea.

These are the two compounding problems that Aegis was built to solve: unnecessary cost, and silent hallucinations. This is a recorded walkthrough of the system, how it works, what it does, and where the design edges are.

`[CUE: Show live app at aegis-llm-gateway.vercel.app/app — 3-panel layout visible]`

---

## Scene 2 — Architecture Overview (1:00–2:30)

Aegis is a seven-stage request pipeline. Every prompt passes through these stages in order, and each stage either acts or passes the request forward.

`[CUE: Show README Mermaid diagram or scroll to System Architecture in README]`

Stage one is a security gate — PII scan plus prompt injection detection — running on deterministic rules before any model is ever called. If your prompt contains a social security number or says "ignore all previous instructions," the request is blocked with a four hundred error. No API call made.

Stage two is a semantic cache. Every incoming prompt is embedded with a sentence transformer model, and compared against previously seen queries using cosine similarity. If the similarity exceeds point eight five, you get the cached response back in about five milliseconds at zero cost.

Stage three is the complexity classifier. This is where Aegis scores your prompt from zero to one across four factors: vocabulary richness, structural complexity, question type, and domain similarity. That score determines which model tier handles the request.

Stage four is the domain hard gate. If the classifier detects a legal, medical, or financial query, the request is unconditionally routed to GPT-4o — no matter what the complexity score says. Misrouting a medical question to a free model creates real harm risk that cost savings cannot justify.

Stage five is the LLM call — routed to whichever model the classifier selected, with three-retry exponential backoff and provider rotation across primary and alternate providers per tier.

Stage six is the causal risk check. This is the novel part. Aegis takes your original prompt, generates two semantically equivalent paraphrases, sends them to the same model at temperature zero, and measures how much the responses diverge. High divergence — above a variance threshold of point three five — means the model's answer was anchored to surface features of your prompt, not to underlying knowledge. That's a hallucination signal.

Stage seven is the SQLite log. Every request is recorded with cost, model, latency, domain, risk level, and whether it was a cache hit.

---

## Scene 3 — Live Demo: Cost Routing (2:30–4:30)

Let me show you the routing in action. I'm going to send two prompts that are very different in complexity.

`[CUE: Open Prompt Library modal — click "Prompt Library" button]`

First, a simple factual query.

`[CUE: Select "What is the capital of France?" from Routing — Simple section]`

`[CUE: Watch the pipeline stages appear in StreamingStatus, then RoutingFlow loads]`

The classifier scored this at around point zero five — far below the first tier boundary at point two zero. It routed to Llama 3.1 via Groq. Total cost: effectively zero. Response time under two seconds.

Now a genuinely complex prompt.

`[CUE: Select the microservices + event sourcing + CQRS prompt from Routing — Complex]`

`[CUE: Watch routing — higher complexity score, higher tier model selected]`

The classifier puts this in the premium tier — above point six five — and routes it to GPT-4o-mini or GPT-4o depending on the exact score. The cost is higher, but it's matched to the complexity of the request. A simple factual query never touches a premium model. That's the routing guarantee.

---

## Scene 4 — Domain Hard Gate (4:30–5:30)

`[CUE: Select the California non-compete legal prompt from Domain Gate — Legal section]`

`[CUE: Watch RoutingFlow — look for "Forced" label on the routing decision]`

Notice what happened. Regardless of the complexity score, the routing decision shows a forced override. The domain classifier identified this as a legal query, and the system bypassed the complexity tier entirely. GPT-4o handled it. This is a design invariant — it cannot be overridden by any other system component.

---

## Scene 5 — Semantic Cache (5:30–6:30)

I'm going to send that same legal prompt again.

`[CUE: Re-submit the California non-compete prompt]`

`[CUE: Watch for "Cache Hit" label and near-zero latency in RoutingFlow]`

Cache hit. The response came back in under ten milliseconds at zero API cost. The semantic cache doesn't require an exact text match — it matched the embedded meaning of the prompt against the previously cached query. A paraphrase of the same question would also hit the cache.

---

## Scene 6 — Hallucination Detection (6:30–8:00)

Now the part that's hardest to show with any other system.

`[CUE: Select the "Dr. James Mitchell 2019 Harvard study" prompt from Hallucination Detection section]`

`[CUE: Watch risk level badge in ResponseCard — should show HIGH]`

The model responded with confident-sounding details about a study that does not exist. Aegis caught it. Here's how.

`[CUE: Expand or point to the causal analysis section in ResponseCard]`

Aegis generated two paraphrases of the original prompt — reworded versions that ask the same thing — and sent them to the same model at temperature zero. The responses diverged significantly. A model that actually knew about this study would give consistent answers regardless of how the question was phrased. Divergence above point three five means the answer was anchored to the prompt's surface features, not to knowledge. That's Pearl's Rung Two intervention applied to reliability scoring.

This works without any external knowledge base or fact-checking API. It's purely structural.

---

## Scene 7 — Causal Analysis (8:00–9:30)

`[CUE: Switch to Dashboard panel — scroll to DoWhy Causal Analysis card]`

This is the post-hoc causal validation layer. The system exposes an endpoint that runs a DoWhy backdoor adjustment on the accumulated request log. The question it answers is: does domain classification causally increase routing cost, after controlling for complexity score as a confounder?

The answer is yes — by design. Sensitive domain queries get routed to GPT-4o unconditionally, which is more expensive. The DoWhy analysis estimates the size of that causal effect. The placebo refutation test — which permutes the treatment label — shows a substantially reduced effect, confirming that the relationship is causal rather than a confounded correlation.

This matters because it gives an honest, statistically grounded account of what the system is actually doing and why. It's not magic — it's a documented causal mechanism.

`[CUE: Show the causal effect estimate and refutation pass/fail badge]`

---

## Scene 8 — Code Walkthrough (9:30–10:30)

Let me show you three files that are doing the real work.

`[CUE: Open backend/app/services/classifier.py]`

The complexity classifier assigns a weighted score across four factors. The question-type sub-score carries the most weight at point three five — because whether a prompt is asking a factual question, an analytical one, or a system design question is the strongest single signal for which model tier it needs. The routing confidence formula gives you a number between point five and point nine five — higher confidence when the score is deep inside a tier, lower when it's near a boundary.

`[CUE: Open backend/app/services/hallucination_detector.py]`

The hallucination detector runs three calls: one for each paraphrase, and compares the responses using cosine similarity of their embeddings. Variance above point three five is flagged as HIGH risk. This threshold is a calibrated heuristic — not a validated ROC cutoff — which is worth being honest about. The gap between factual queries, which consistently produce variance below point two, and hallucination-prone queries, which produce variance above point four, gives a natural operating range. Point three five sits in the upper half of that gap, biasing toward precision.

`[CUE: Open backend/app/services/security.py]`

The security gate runs before any of the above. PII patterns, injection keywords, and domain classification — all deterministic, all blocking before any model call is made.

---

## Scene 9 — Results and Limitations (10:30–11:30)

`[CUE: Switch to Dashboard — KPI tiles visible]`

On the dashboard you can see live metrics: total requests routed, cache hit rate, estimated cost savings relative to a GPT-4o baseline, average latency, and hallucinations flagged. These numbers accumulate from real requests made during the session.

The cost savings estimate is based on the difference between what each request actually cost and what it would have cost at GPT-4o rates. On the synthetic seed workload the savings run between forty and sixty percent. That's a model-based estimate, not a production measurement — and it's worth being clear about that distinction.

What this system does not do: it does not catch consistent hallucinations. A model that confidently gives the same wrong answer every time will pass the variance check. It does not replace domain expert review. The security gate and domain hard-gate are scope limits, not safety certifications.

---

## Scene 10 — Learnings and Close (11:30–12:00)

The most useful thing I learned building this: you can get most of the benefit from a causal framing of hallucination detection without running DoWhy at request time. The paraphrase variance check is cheap, fast, and grounded in Pearl's intervention calculus — if changing the surface form of the question while holding the meaning constant destabilizes the answer, that's a causal signal about the model's grounding.

The hardest part was being honest about what the system claims. Calling a heuristic threshold "empirically validated" is easy. Admitting it's a heuristic that warrants formal calibration is harder but more defensible.

`[CUE: Show live app URL: aegis-llm-gateway.vercel.app]`

The system is live. The source is on GitHub. All fifty-seven tests pass with no live API calls required. Thank you.

---

## Recording Notes

- **Total target:** 10–12 minutes at a comfortable narration pace (~130 words/minute = ~1,500 words; this script is ~1,450 words)
- **ElevenLabs settings:** Use a measured, technical delivery voice. No dramatic pauses. Treat it like a conference talk, not a product demo.
- **Screen recording:** Record the browser at full resolution. For code sections, use VS Code with the file open — syntax highlighting makes it readable.
- **Cut order:** Record narration first, then record screen sections, then sync in post. The script is written so each `[CUE]` corresponds to a single visible state change.
- **Canvas submission:** Upload to YouTube (unlisted is fine), then paste the link in the Canvas submission along with the app URL and the project zip.
