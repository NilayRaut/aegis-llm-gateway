"""
Seed data for Aegis dashboard demo.

Seeds 50 realistic requests so the dashboard shows non-zero stats
the moment the professor opens it — before any real prompts are sent.

Idempotent: checks for existing seed records before inserting.
Uses random.seed(42) for deterministic, reproducible data.
Timestamps spread across the last 24 hours.
"""

import asyncio
import logging
import random
import sqlite3
import uuid
from datetime import datetime, timedelta

from app.db import DB_PATH

logger = logging.getLogger(__name__)

# Fixed seed for reproducible demo data
random.seed(42)


def _build_seed_records() -> list[dict]:
    """
    Build 50 demo request records with a realistic model distribution.

    Distribution:
      8  × llama3.1           (free, general)
      10 × gemini-2.0-flash  ($0.000008, general/technical)
      12 × gpt-4o-mini       ($0.000015, general)
       5 × claude-haiku      ($0.000025, general)
       7 × gpt-4o            ($0.0003, technical, SAFE)
       3 × gpt-4o            ($0.0003, legal/medical, HIGH risk)
       5 × gpt-4o-mini       ($0, cache hits)
      ──
      50 total
    """
    records = []
    now = datetime.utcnow()

    def ts(i: int) -> str:
        """Spread 50 records across last 24 hours."""
        return (now - timedelta(hours=i * 0.48)).strftime("%Y-%m-%d %H:%M:%S")

    idx = 0

    # Group 1: llama3.1 (8 records, free, general)
    for _ in range(8):
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "llama3.1",
            "provider": "ollama",
            "cost_usd": 0.0,
            "latency_ms": random.randint(50, 200),
            "complexity_score": round(random.uniform(0.0, 0.18), 3),
            "domain": "general",
            "cache_hit": 0,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    # Group 2: gemini-2.0-flash (10 records)
    domains_g2 = ["general"] * 6 + ["technical"] * 4
    random.shuffle(domains_g2)
    for d in domains_g2:
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "gemini-2.0-flash",
            "provider": "google",
            "cost_usd": round(random.uniform(0.000006, 0.000010), 8),
            "latency_ms": random.randint(400, 800),
            "complexity_score": round(random.uniform(0.22, 0.38), 3),
            "domain": d,
            "cache_hit": 0,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    # Group 3: gpt-4o-mini (12 records, general)
    for _ in range(12):
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "gpt-4o-mini",
            "provider": "openai",
            "cost_usd": round(random.uniform(0.000012, 0.000018), 8),
            "latency_ms": random.randint(600, 1200),
            "complexity_score": round(random.uniform(0.66, 0.78), 3),
            "domain": "general",
            "cache_hit": 0,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    # Group 4: claude-haiku (5 records, general)
    for _ in range(5):
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "claude-3-5-haiku-20241022",
            "provider": "anthropic",
            "cost_usd": round(random.uniform(0.000020, 0.000030), 8),
            "latency_ms": random.randint(800, 1500),
            "complexity_score": round(random.uniform(0.47, 0.63), 3),
            "domain": "general",
            "cache_hit": 0,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    # Group 5: gpt-4o — technical, SAFE (7 records)
    for _ in range(7):
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "gpt-4o",
            "provider": "openai",
            "cost_usd": round(random.uniform(0.00025, 0.00035), 8),
            "latency_ms": random.randint(1500, 3000),
            "complexity_score": round(random.uniform(0.82, 0.98), 3),
            "domain": "technical",
            "cache_hit": 0,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    # Group 6: gpt-4o — legal/medical, HIGH risk (3 records)
    high_risk_domains = ["legal", "medical", "legal"]
    for d in high_risk_domains:
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "gpt-4o",
            "provider": "openai",
            "cost_usd": round(random.uniform(0.00025, 0.00035), 8),
            "latency_ms": random.randint(1500, 3000),
            "complexity_score": round(random.uniform(0.82, 0.98), 3),
            "domain": d,
            "cache_hit": 0,
            "risk_level": "HIGH",
            "security_blocked": 0,
        })
        idx += 1

    # Group 7: cache hits (5 records, gpt-4o-mini, near-zero cost + latency)
    for _ in range(5):
        records.append({
            "id": str(uuid.uuid4()),
            "timestamp": ts(idx),
            "model_used": "gpt-4o-mini",
            "provider": "openai",
            "cost_usd": 0.0,
            "latency_ms": random.randint(5, 15),
            "complexity_score": round(random.uniform(0.66, 0.78), 3),
            "domain": "general",
            "cache_hit": 1,
            "risk_level": "SAFE",
            "security_blocked": 0,
        })
        idx += 1

    return records


async def seed_if_empty() -> None:
    """
    Insert 50 demo records if no seed data exists yet. Idempotent.
    Uses direct sqlite3 (not log_request) so it can set is_seed=1.
    """
    def _check_and_seed():
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")

        count = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE is_seed = 1"
        ).fetchone()[0]

        if count > 0:
            conn.close()
            logger.info("Seed data already present (%d records) — skipping", count)
            return

        records = _build_seed_records()
        conn.executemany(
            """INSERT OR IGNORE INTO requests
               (id, timestamp, model_used, provider, cost_usd, latency_ms,
                complexity_score, domain, cache_hit, risk_level, security_blocked, is_seed)
               VALUES
               (:id, :timestamp, :model_used, :provider, :cost_usd, :latency_ms,
                :complexity_score, :domain, :cache_hit, :risk_level, :security_blocked, 1)""",
            records,
        )
        conn.commit()
        conn.close()
        logger.info("Seed data inserted: %d demo records", len(records))

    await asyncio.to_thread(_check_and_seed)
