"""weight_ledger -- append gate verdicts to a durable JSONL ledger.

data/cache/intel_claims/claim_weights.jsonl. Idempotent by (family, metric,
method): re-running the gate REPLACES the prior row for that key rather than
duplicating. The row is a calibration record only -- edge_claimed is hard-wired
False and no dollar/ROI field exists.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from scripts.platformkit.intel_weighting.relevance_gate import GateResult, METHOD

REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER = REPO_ROOT / "data" / "cache" / "intel_claims" / "claim_weights.jsonl"


def _row(g: GateResult) -> dict:
    return {
        "family": g.family,
        "metric": g.metric,
        "sport": g.sport,
        "entity_mapping": g.entity_mapping,
        "n_games": g.n_games,
        "brier_base": g.brier_base,
        "brier_cond": g.brier_cond,
        "delta": g.delta,
        "delta_trunc80": g.delta_trunc80,
        "dm_p": g.dm_p,
        "verdict": g.verdict,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": METHOD,
        "edge_claimed": False,
        "caveats": g.caveats,
    }


def _key(r: dict) -> tuple:
    return (r.get("family"), r.get("metric"), r.get("method"))


def append_results(results: Iterable[GateResult], ledger: Path | None = None) -> Path:
    """Upsert rows keyed by (family, metric, method). Rewrites atomically."""
    ledger = ledger or LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[_key(r)] = r
    for g in results:
        r = _row(g)
        existing[_key(r)] = r
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for r in existing.values():
            f.write(json.dumps(r) + "\n")
    tmp.replace(ledger)
    return ledger


def read_ledger(ledger: Path | None = None) -> List[dict]:
    ledger = ledger or LEDGER
    if not ledger.exists():
        return []
    rows = []
    for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows
