"""
Shared fixtures for Aegis backend tests.

Strategy:
- Unit tests (security, classifier, cache, hallucination) test services directly.
- Route tests get an isolated SQLite DB (tmp_path) and all LLM calls mocked.
- Seed data is suppressed in route tests so the DB starts empty and assertions
  on counts are deterministic.
"""

import pytest
from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient


@pytest.fixture
def test_client(tmp_path):
    """
    FastAPI TestClient with:
    - Isolated SQLite DB (tmp_path / test.db)
    - seed_if_empty suppressed (empty DB = deterministic counts)
    """
    db_file = str(tmp_path / "test.db")

    with (
        patch("app.db.DB_PATH", db_file),
        patch("app.seed_data.seed_if_empty", new=AsyncMock()),
    ):
        # Import after patching so startup uses the patched DB path
        from main import app

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


# ── Fake LLM router response ────────────────────────────────────────────────

FAKE_ROUTER_RESULT = {
    "response": "This is a test response.",
    "model_used": "gpt-4o-mini",
    "provider": "openai",
    "complexity_score": 0.45,
    "routing_decision": {
        "model": "gpt-4o-mini",
        "reason": "Standard query routed to gpt-4o-mini for good quality",
        "confidence": 0.8,
        "cache_hit": False,
    },
    "cost": 0.000015,
    "latency_ms": 800,
    "input_tokens": 50,
    "output_tokens": 30,
    "error": None,
}
