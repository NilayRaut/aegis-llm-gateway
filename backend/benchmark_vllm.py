"""
GuideLLM benchmark runner for Aegis vLLM tier.

Measures TTFT, ITL, and throughput against a live vLLM server using prompts
that mirror Aegis's complexity distribution (2 simple / 4 mid / 3 complex / 1 factual).

Usage (GPU session with vLLM running):
    pip install guidellm
    python benchmark_vllm.py --base-url http://localhost:8000/v1 \
                              --model meta-llama/Llama-3.1-8B-Instruct

Results saved to benchmark_results.json (gitignored).
"""

import argparse
import json
import sys
import time
import statistics


PROMPTS = [
    # simple (complexity ~0.05–0.15)
    "What is 2 + 2?",
    "What color is the sky?",
    # mid (complexity ~0.25–0.40)
    "Explain the difference between RAM and ROM in 2–3 sentences.",
    "What are the main causes of the French Revolution?",
    "Summarize the plot of Romeo and Juliet.",
    "How does photosynthesis work?",
    # complex (complexity ~0.55–0.75)
    "Compare and contrast supervised and unsupervised machine learning. Include use cases for each.",
    "Explain transformer attention mechanisms and why they replaced RNNs for sequence modeling.",
    "Describe the CAP theorem and its practical implications for distributed database design.",
    # factual / hallucination-prone (triggers Tier 3 in live Aegis)
    "What were the exact revenue figures reported by OpenAI in their 2023 annual report?",
]


def run_openai_benchmark(base_url: str, model: str) -> dict:
    """
    Use the openai SDK (already a dep) to drive individual calls and collect
    timing data. Returns a dict with TTFT p50/p95, ITL p50/p95, throughput.

    TTFT = time to first chunk (streaming mode).
    ITL  = (total_latency - ttft) / (output_tokens - 1)  per request, averaged.
    Throughput = total output tokens / total wall-clock seconds.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package not found. Install with: pip install openai")
        sys.exit(1)

    client = OpenAI(base_url=base_url, api_key="EMPTY")

    ttfts: list[float] = []
    itls: list[float] = []
    total_tokens = 0
    wall_start = time.time()

    print(f"\nRunning {len(PROMPTS)} prompts against {base_url} (model={model})\n")

    for i, prompt in enumerate(PROMPTS, 1):
        messages = [{"role": "user", "content": prompt}]
        req_start = time.time()
        first_token_time: float | None = None
        output_tokens = 0

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=256,
            temperature=0.0,
            stream=True,
        )

        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time()
            delta = chunk.choices[0].delta.content or ""
            if delta:
                output_tokens += len(delta.split())  # word-count proxy for tokens

        req_end = time.time()
        total_latency_ms = (req_end - req_start) * 1000
        ttft_ms = (first_token_time - req_start) * 1000 if first_token_time else total_latency_ms

        ttfts.append(ttft_ms)
        total_tokens += output_tokens

        # ITL: only meaningful when output > 1 token
        if output_tokens > 1 and first_token_time:
            generation_ms = (req_end - first_token_time) * 1000
            itls.append(generation_ms / (output_tokens - 1))

        print(f"  [{i:2d}/{len(PROMPTS)}] TTFT={ttft_ms:.1f}ms  total={total_latency_ms:.0f}ms  out≈{output_tokens}tok")

    wall_total = time.time() - wall_start
    throughput_tok_s = total_tokens / wall_total if wall_total > 0 else 0.0
    throughput_req_s = len(PROMPTS) / wall_total if wall_total > 0 else 0.0

    def pct(data: list[float], p: int) -> float:
        if not data:
            return 0.0
        idx = max(0, int(len(data) * p / 100) - 1)
        return sorted(data)[idx]

    results = {
        "model": model,
        "base_url": base_url,
        "n_prompts": len(PROMPTS),
        "ttft_ms": {
            "p50": round(pct(ttfts, 50), 1),
            "p95": round(pct(ttfts, 95), 1),
            "mean": round(statistics.mean(ttfts), 1),
        },
        "itl_ms": {
            "p50": round(pct(itls, 50), 1) if itls else None,
            "p95": round(pct(itls, 95), 1) if itls else None,
            "mean": round(statistics.mean(itls), 1) if itls else None,
        },
        "throughput": {
            "tokens_per_s": round(throughput_tok_s, 1),
            "requests_per_s": round(throughput_req_s, 3),
        },
        "total_wall_s": round(wall_total, 2),
    }
    return results


def run_guidellm_benchmark(base_url: str, model: str) -> dict:
    """
    Drive benchmark via guidellm if installed.
    Falls back to run_openai_benchmark() if guidellm is not available.
    """
    try:
        from guidellm import GuideLLMRunner  # noqa: F401
        from guidellm.benchmark import BenchmarkConfig, RequestConfig
    except ImportError:
        print("guidellm not installed — falling back to openai streaming benchmark.")
        print("To use GuideLLM: pip install guidellm\n")
        return run_openai_benchmark(base_url, model)

    print("GuideLLM detected — running managed benchmark...")
    config = BenchmarkConfig(
        target=base_url,
        model=model,
        data=PROMPTS,
        request_config=RequestConfig(max_tokens=256),
        output_path="benchmark_results_raw.json",
    )
    runner = GuideLLMRunner(config=config)
    report = runner.run()

    return {
        "model": model,
        "base_url": base_url,
        "source": "guidellm",
        "ttft_ms": {
            "p50": getattr(report, "ttft_ms_p50", None),
            "p95": getattr(report, "ttft_ms_p95", None),
        },
        "itl_ms": {
            "p50": getattr(report, "itl_ms_p50", None),
            "p95": getattr(report, "itl_ms_p95", None),
        },
        "throughput": {
            "tokens_per_s": getattr(report, "output_tokens_per_second", None),
            "requests_per_s": getattr(report, "requests_per_second", None),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Aegis vLLM tier with GuideLLM")
    parser.add_argument("--base-url", default="http://localhost:8000/v1",
                        help="vLLM server base URL (default: http://localhost:8000/v1)")
    parser.add_argument("--model", default="meta-llama/Llama-3.1-8B-Instruct",
                        help="Model name served by vLLM")
    parser.add_argument("--out", default="benchmark_results.json",
                        help="Output JSON path (default: benchmark_results.json)")
    args = parser.parse_args()

    results = run_guidellm_benchmark(args.base_url, args.model)

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    print("\n--- Results ---")
    print(f"TTFT  p50={results['ttft_ms']['p50']}ms  p95={results['ttft_ms']['p95']}ms")
    if results.get("itl_ms") and results["itl_ms"].get("p50") is not None:
        print(f"ITL   p50={results['itl_ms']['p50']}ms  p95={results['itl_ms']['p95']}ms")
    thr = results.get("throughput", {})
    print(f"Throughput  {thr.get('tokens_per_s')} tok/s  /  {thr.get('requests_per_s')} req/s")
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
