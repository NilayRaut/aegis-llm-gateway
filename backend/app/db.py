"""
SQLite database layer for Aegis.

Uses standard library sqlite3 wrapped in asyncio.to_thread() for
async compatibility — no new dependencies needed (no aiosqlite/asyncpg).

DB file: backend/aegis.db
Path is anchored to this file's location so it works regardless of
the current working directory when uvicorn is launched.
"""

import asyncio
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# Resolve path relative to this file: backend/app/db.py → backend/aegis.db
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aegis.db")

# GPT-4o baseline cost per query (used to calculate savings)
# $0.0025 ≈ average GPT-4o cost for a 300-token input / 200-token output query
GPT4O_BASELINE_COST = 0.0025


def _get_conn() -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode for safe concurrent writes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_db() -> None:
    """Create the requests table if it doesn't exist. Called once at startup."""
    def _init():
        conn = _get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id                TEXT PRIMARY KEY,
                timestamp         TEXT DEFAULT (datetime('now')),
                model_used        TEXT NOT NULL,
                provider          TEXT DEFAULT '',
                cost_usd          REAL DEFAULT 0.0,
                latency_ms        INTEGER DEFAULT 0,
                complexity_score  REAL DEFAULT 0.0,
                domain            TEXT DEFAULT 'general',
                cache_hit         INTEGER DEFAULT 0,
                risk_level        TEXT DEFAULT 'SAFE',
                security_blocked  INTEGER DEFAULT 0,
                is_seed           INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
        logger.info("DB initialized at %s", DB_PATH)

    await asyncio.to_thread(_init)


async def log_request(
    id: str,
    model_used: str,
    provider: str,
    cost_usd: float,
    latency_ms: int,
    complexity_score: float,
    domain: str,
    cache_hit: bool,
    risk_level: str,
    security_blocked: bool,
) -> None:
    """Insert a request record. INSERT OR IGNORE protects against duplicate IDs."""
    def _insert():
        conn = _get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO requests
               (id, model_used, provider, cost_usd, latency_ms,
                complexity_score, domain, cache_hit, risk_level, security_blocked)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id,
                model_used,
                provider,
                cost_usd,
                latency_ms,
                complexity_score,
                domain,
                int(cache_hit),
                risk_level,
                int(security_blocked),
            ),
        )
        conn.commit()
        conn.close()

    await asyncio.to_thread(_insert)


async def get_recent_requests(limit: int = 50) -> list[dict]:
    """Return the last N requests ordered by timestamp descending."""
    def _query():
        conn = _get_conn()
        rows = conn.execute(
            """SELECT id, timestamp, model_used, provider, cost_usd, latency_ms,
                      complexity_score, domain, cache_hit, risk_level, security_blocked
               FROM requests
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await asyncio.to_thread(_query)


async def get_stats() -> dict:
    """
    Aggregate statistics for the dashboard.

    cost_savings = (total_requests × GPT-4o baseline) − actual_cost
    avg_latency  excludes cache hits (they're artificially fast)
    hallucinations_caught = requests with risk_level MEDIUM or HIGH
    """
    def _query():
        conn = _get_conn()

        total = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]

        cache_hits = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE cache_hit = 1"
        ).fetchone()[0]
        cache_hit_rate = (cache_hits / total * 100.0) if total > 0 else 0.0

        actual_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM requests"
        ).fetchone()[0]
        baseline_cost = total * GPT4O_BASELINE_COST
        cost_savings = max(baseline_cost - actual_cost, 0.0)

        avg_latency_raw = conn.execute(
            "SELECT COALESCE(AVG(latency_ms), 0) FROM requests WHERE cache_hit = 0"
        ).fetchone()[0]

        hallucinations = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE risk_level IN ('MEDIUM', 'HIGH')"
        ).fetchone()[0]

        rows = conn.execute(
            "SELECT model_used, COUNT(*) as cnt FROM requests GROUP BY model_used"
        ).fetchall()
        model_dist = {row["model_used"]: row["cnt"] for row in rows}

        conn.close()

        return {
            "total_requests": total,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "cost_savings": round(cost_savings, 6),
            "avg_latency_ms": int(avg_latency_raw),
            "hallucinations_caught": hallucinations,
            "model_distribution": model_dist,
        }

    return await asyncio.to_thread(_query)


async def get_provider_stats() -> list[dict]:
    """
    Per-provider aggregates for the Provider Health Board panel.

    Returns one row per provider that has been used, with total queries,
    average latency (excluding cache hits), and the timestamp of the most
    recent request.  Providers with no recorded requests are omitted here;
    the API layer merges in defaults for unconfigured ones.
    """
    def _query():
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT
                provider,
                COUNT(*)                        AS total_queries,
                COALESCE(AVG(latency_ms), 0)    AS avg_latency_ms,
                MAX(timestamp)                  AS last_seen
            FROM requests
            WHERE provider != ''
              AND cache_hit  = 0
            GROUP BY provider
            ORDER BY total_queries DESC
            """
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    return await asyncio.to_thread(_query)
