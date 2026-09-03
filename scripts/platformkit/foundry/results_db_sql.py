"""SQL definitions and row adapters for :mod:`results_db`."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from scripts.platformkit.eval_gate.deflated_metrics import deflated_p as _deflated_p
from scripts.platformkit.foundry.grammar import Hypothesis

_HYPOTHESIS_RAW = ("sport", "feature", "transform", "params", "conditioning", "horizon", "market")
_RESULT_FIELDS = ("hash", "tier", "corpus", "corpus_unit", "corpus_sha", "n", "n_eff",
                  "brier_model", "brier_close", "dm_stat", "raw_p", "k_family", "k_global",
                  "deflated_p", "pbo", "verdict", "artifact_path", "prereg_sha256", "run_at")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS hypothesis(
    hash TEXT PRIMARY KEY, family TEXT, sport TEXT, feature TEXT, transform TEXT,
    params TEXT, conditioning TEXT, horizon TEXT, market TEXT,
    runtime_available INTEGER, created_at TEXT, grammar_version TEXT);
CREATE TABLE IF NOT EXISTS result(
    id INTEGER PRIMARY KEY, hash TEXT REFERENCES hypothesis(hash), tier TEXT, corpus TEXT,
    corpus_unit TEXT, corpus_sha TEXT, n INTEGER, n_eff REAL, brier_model REAL,
    brier_close REAL, dm_stat REAL, raw_p REAL, k_family INTEGER, k_global INTEGER,
    deflated_p REAL, pbo REAL, verdict TEXT, artifact_path TEXT, prereg_sha256 TEXT,
    run_at TEXT, UNIQUE(hash, tier, corpus, corpus_unit, corpus_sha));
CREATE TABLE IF NOT EXISTS queue(
    hash TEXT PRIMARY KEY, tier TEXT, enqueued_at TEXT, claimed_at TEXT, lease_until TEXT,
    claimer TEXT);
"""


@dataclass(frozen=True)
class TierResult:
    """The minimal shape `record()` accepts."""

    hash: str
    tier: str
    corpus: str
    corpus_unit: str
    corpus_sha: str
    n: int
    n_eff: float
    brier_model: float
    brier_close: float
    dm_stat: float
    raw_p: float
    k_family: Optional[int]
    k_global: int
    deflated_p: float
    pbo: Optional[float]
    verdict: str
    artifact_path: str
    prereg_sha256: Optional[str] = None
    run_at: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recompute_deflated_p(row: Mapping[str, Any], k_now: int) -> Optional[float]:
    """Return the current-K deflated p for a stored row."""
    raw_p = row.get("raw_p")
    return None if raw_p is None else _deflated_p(float(raw_p), int(k_now))


def _hypothesis(row: sqlite3.Row) -> Hypothesis:
    return Hypothesis(
        sport=row["sport"], feature=row["feature"], transform=row["transform"],
        params=tuple(tuple(pair) for pair in json.loads(row["params"])),
        conditioning=frozenset(json.loads(row["conditioning"])),
        horizon=row["horizon"], market=row["market"], family=row["family"] or "",
        runtime_available=bool(row["runtime_available"]))
