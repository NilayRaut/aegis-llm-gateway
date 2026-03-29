"""
verify_apis.py — Smoke-test all three LLM APIs before starting Session 1.

Run from the notebooks/ directory:
    python verify_apis.py

Keys are loaded from ../backend/.env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / "backend" / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

results = {}  # api_name -> True/False

# ── OpenAI ──────────────────────────────────────────────────────────────────
print("=" * 60)
print("Testing OpenAI (gpt-4o-mini) ...")
try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Reply with the single word: verified"}],
        max_tokens=5,
    )
    text = response.choices[0].message.content
    if "verified" in text.lower():
        print(f"  PASS  gpt-4o-mini → '{text.strip()}'")
        results["OpenAI"] = True
    else:
        print(f"  FAIL  gpt-4o-mini → unexpected response: '{text.strip()}'")
        results["OpenAI"] = False
except Exception as e:
    print(f"  FAIL  gpt-4o-mini → {e}")
    results["OpenAI"] = False

# ── Anthropic ────────────────────────────────────────────────────────────────
print("Testing Anthropic (claude-haiku-4-5-20251001) ...")
try:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5,
        messages=[{"role": "user", "content": "Reply with the single word: verified"}],
    )
    text = response.content[0].text
    if "verified" in text.lower():
        print(f"  PASS  claude-haiku-4-5-20251001 → '{text.strip()}'")
        results["Anthropic"] = True
    else:
        print(f"  FAIL  claude-haiku-4-5-20251001 → unexpected response: '{text.strip()}'")
        results["Anthropic"] = False
except Exception as e:
    print(f"  FAIL  claude-haiku-4-5-20251001 → {e}")
    results["Anthropic"] = False

# ── Google ───────────────────────────────────────────────────────────────────
print("Testing Google (gemini-2.5-flash) ...")
try:
    from google import genai
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with the single word: verified",
    )
    text = response.text
    if "verified" in text.lower():
        print(f"  PASS  gemini-2.5-flash → '{text.strip()}'")
        results["Google"] = True
    else:
        print(f"  FAIL  gemini-2.5-flash → unexpected response: '{text.strip()}'")
        results["Google"] = False
except Exception as e:
    print(f"  FAIL  gemini-2.5-flash → {e}")
    results["Google"] = False

# ── Library import checks ────────────────────────────────────────────────────
print("=" * 60)
print("Checking critical library imports ...")

print("  sentence-transformers ...", end=" ")
try:
    import sentence_transformers  # noqa: F401
    print("PASS")
except Exception as e:
    print(f"FAIL  → {e}")

print("  dowhy               ...", end=" ")
try:
    import dowhy  # noqa: F401
    print("PASS")
except Exception as e:
    print(f"FAIL  → {e}")

# ── Summary ──────────────────────────────────────────────────────────────────
print("=" * 60)
passing = sum(results.values())
total = len(results)
print(f"APIs ready for benchmark: {passing}/{total}")

if passing == total:
    print("All APIs operational. Ready to proceed to Session 1.")
elif passing == 1:
    print(
        "CRITICAL: Only 1 API available. Session 1 will produce "
        "incomplete benchmark results. Resolve before continuing."
    )
elif passing < 2:
    print(
        "WARNING: benchmark requires at least 2 working APIs. "
        "Fix failing keys before proceeding to Session 1."
    )
else:
    # 2 out of 3 — warn but not critical
    failing = [k for k, v in results.items() if not v]
    print(
        f"WARNING: benchmark requires at least 2 working APIs. "
        f"Failing: {', '.join(failing)}. Fix before proceeding to Session 1."
    )
