"""
Shared helpers for the eval scripts (eval_tier3.py, eval_recalibration.py).

Provides a provenance header (git commit, UTC date, embedding model, θ sweep)
and binary-classification metrics computed in code, so every number reported
from an eval run can be traced back to a committed JSON file under
eval/results/.

This module makes no network or LLM calls.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "eval" / "results"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_slug(dt: datetime) -> str:
    """Filesystem-safe UTC timestamp, e.g. 20261107T153000Z."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def git_info() -> dict:
    """Commit hash of the checkout running the eval, and whether it had uncommitted changes."""

    def _git(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            return None

    status = _git("status", "--porcelain")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
    }


def confusion_metrics(labels: list[int], preds: list[int]) -> dict:
    """Precision / recall / F1 for the positive class (1) with raw TP/FP/FN/TN counts."""
    tp = sum(1 for l, p in zip(labels, preds) if l == 1 and p == 1)
    fp = sum(1 for l, p in zip(labels, preds) if l == 0 and p == 1)
    fn = sum(1 for l, p in zip(labels, preds) if l == 1 and p == 0)
    tn = sum(1 for l, p in zip(labels, preds) if l == 0 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "n": len(labels),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def write_results(prefix: str, started_at: datetime, payload: dict) -> Path:
    """Write payload to eval/results/<prefix>_<UTC timestamp>.json and return the path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{prefix}_{timestamp_slug(started_at)}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path
