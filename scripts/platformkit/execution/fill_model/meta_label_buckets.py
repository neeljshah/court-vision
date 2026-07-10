"""scripts.platformkit.execution.fill_model.meta_label_buckets -- MEASUREMENT
ONLY: for settled paper Kalshi bets with a model-vs-market divergence at
entry, bucket by divergence size (+ tier) and report the WITHIN-VENUE CLV-
positive rate per bucket with a Wilson CI. Answers "which divergence buckets
are trustworthy vs noise" -- CLV is the yardstick, never $/ROI.

STEP-0 PREMISE CHECK (2026-07-11): data/frontend/clv_ledger.jsonl has 743
kalshi rows; 312 are graded, but only 186 have clv_is_proxy == False (a REAL
Kalshi close, not a cross-venue proxy). Per the crossvenue-CLV-is-basis-not-
edge landmine, only those 186 true_close rows are used here -- proxy-close
rows are dropped, not blended in. Of those, 160 have a usable 'edge' field
(model_prob - market_prob, known at ORDER time, no leak) and 26 have tier but
no edge (arb rows) -- excluded from the edge-quartile table, included only in
the tier table. n=186 is too thin for a reliable walk-forward classifier with
multiple continuous features (would overfit on <200 rows) -- this ships the
honest bucket table only, per rails.
Label: beat_close (bool, already computed in the ledger from clv_pct > 0).
ADJUDICATED 2026-07-11 (meta_label_replication.py): the all-quartiles->50%
pattern is an ORDER-SELECTION artifact -- no bucket replicates on the
independent ingame_grade_joined checkpoint corpus (ARTIFACT_CONFIRMED, see
docs/research/meta_label_replication_2026-07-11.md). This table stays
MEASUREMENT ONLY; never weight/gate orders by these buckets.
INVARIANTS: <=300 LOC; ASCII; stdlib only; local-only output; never writes
data/registry/; no $/ROI/edge claim.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/fill_model/test_meta_label_buckets.py -q
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution.book_replay import load_jsonl
from scripts.platformkit.execution.fill_model.fill_realism import LEDGER_PATH

MIN_BUCKET_N = 10  # below this, a bucket's rate is noise -- flagged, not hidden


def load_true_close_kalshi_bets(sport: Optional[str] = None) -> List[Dict[str, Any]]:
    """Graded, within-venue (clv_is_proxy is False) kalshi ledger rows."""
    out: List[Dict[str, Any]] = []
    for r in load_jsonl(LEDGER_PATH):
        if r.get("taken_book") != "kalshi" or not r.get("graded") or r.get("clv_is_proxy") is not False:
            continue
        if r.get("beat_close") is None:
            continue
        if sport is not None and r.get("sport") != sport:
            continue
        out.append(r)
    return out


def wilson_ci(k: int, n: int, z: float = 1.96) -> Optional[List[float]]:
    """Wilson score 95% CI for a binomial rate, [lo, hi] rounded to 4dp. None if n==0."""
    if n == 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def _bucket_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    k = sum(1 for r in rows if r.get("beat_close"))
    ci = wilson_ci(k, n)
    return {
        "n": n,
        "clv_positive_n": k,
        "clv_positive_rate": round(k / n, 4) if n else None,
        "clv_positive_ci95": ci,
        "trustworthy": bool(n >= MIN_BUCKET_N),
    }


def edge_quartiles(rows: List[Dict[str, Any]]) -> List[float]:
    """(q25, q50, q75) breakpoints of 'edge' among rows that have one."""
    vals = sorted(r["edge"] for r in rows if r.get("edge") is not None)
    if not vals:
        return [0.0, 0.0, 0.0]
    return [vals[len(vals) // 4], vals[len(vals) // 2], vals[3 * len(vals) // 4]]


def edge_bucket_label(edge: float, qs: List[float]) -> str:
    q25, q50, q75 = qs
    if edge <= q25:
        return "Q1_smallest_divergence"
    if edge <= q50:
        return "Q2"
    if edge <= q75:
        return "Q3"
    return "Q4_largest_divergence"


def build_bucket_table(sport: Optional[str] = None) -> Dict[str, Any]:
    rows = load_true_close_kalshi_bets(sport)
    with_edge = [r for r in rows if r.get("edge") is not None]
    qs = edge_quartiles(with_edge)

    by_edge_q: Dict[str, List[Dict[str, Any]]] = {}
    for r in with_edge:
        by_edge_q.setdefault(edge_bucket_label(r["edge"], qs), []).append(r)
    edge_table = {b: _bucket_stats(rs) for b, rs in sorted(by_edge_q.items())}

    by_tier: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_tier.setdefault(r.get("tier") or "untiered", []).append(r)
    tier_table = {t: _bucket_stats(rs) for t, rs in sorted(by_tier.items())}

    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_sport.setdefault(r.get("sport") or "unknown", []).append(r)
    sport_table = {s: _bucket_stats(rs) for s, rs in sorted(by_sport.items())}

    return {
        "sport_filter": sport,
        "edge_claimed": False,
        "n_total_true_close_kalshi_bets": len(rows),
        "n_with_edge_field": len(with_edge),
        "classifier_verdict": (
            "bucket table only -- n=%d is too thin for a walk-forward classifier "
            "with multiple continuous features (rails: honest bucket table when "
            "n too thin)" % len(rows)
        ),
        "edge_quartile_breakpoints": [round(q, 5) for q in qs],
        "by_edge_quartile": edge_table,
        "by_tier": tier_table,
        "by_sport": sport_table,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="CLV meta-label bucket table, within-venue Kalshi only (no $/edge claim)")
    ap.add_argument("--sport", default=None)
    ap.add_argument("--window", default=None, help="unused, kept for CLI-shape parity with fill_realism")
    args = ap.parse_args()
    print(json.dumps(build_bucket_table(sport=args.sport), ensure_ascii=True, indent=2))
    return 0


__all__ = ["load_true_close_kalshi_bets", "wilson_ci", "edge_quartiles", "edge_bucket_label", "build_bucket_table"]

if __name__ == "__main__":
    raise SystemExit(main())
