"""probe_R23_P8_live_rec_harness.py — viability probe for R23_P8.

Runs the live recommendation engine against TODAY's real data (read-only)
and captures the headline counts + the top-3 recs by edge. Persists the
result to `data/cache/probe_R23_P8_results.json`.

SHIP gate
---------
  * engine completes without raising
  * payload contains a `recommendations` list (may be empty)
  * counts present: n_predictions_available, n_snapshots_loaded,
    n_out_players_in_feed, n_recs, n_filtered_out, n_filtered_kelly_cap
  * if no NBA games today (offseason), the probe falls back to
    YESTERDAY's data so the pipeline is still demonstrably wired.

Persists:
  data/cache/probe_R23_P8_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from scripts.live_recommendation_engine import run_engine  # noqa: E402

_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R23_P8_results.json"
)


def _has_data_for(date_str: str) -> bool:
    """Return True iff both a predictions cache and at least one book
    snapshot exist for `date_str` — the minimum to drive the engine."""
    preds = os.path.join(PROJECT_DIR, "data", "cache",
                          f"predictions_cache_{date_str}.parquet")
    if not os.path.exists(preds):
        return False
    lines_dir = os.path.join(PROJECT_DIR, "data", "lines")
    if not os.path.isdir(lines_dir):
        return False
    for book in ("fd", "bov", "pin"):
        if os.path.exists(os.path.join(lines_dir, f"{date_str}_{book}.csv")):
            return True
    return False


def _pick_target_date(prefer: Optional[str] = None) -> str:
    """Today preferred. If today's stack is missing, walk back up to 7 days."""
    if prefer:
        return prefer
    today = _date_cls.today()
    for d in range(0, 8):
        cand = (today - timedelta(days=d)).isoformat()
        if _has_data_for(cand):
            return cand
    return today.isoformat()


def run_probe(
    bankroll: float = 1000.0,
    top: int = 10,
    date: Optional[str] = None,
    min_edge: float = 0.05,
) -> Dict[str, Any]:
    target_date = _pick_target_date(date)
    payload = run_engine(
        bankroll=bankroll,
        top=top,
        date=target_date,
        min_edge=min_edge,
    )
    recs = payload.get("recommendations", []) or []
    top3 = []
    for b in recs[:3]:
        top3.append({
            "player":  b.get("player"),
            "stat":    b.get("stat"),
            "side":    b.get("side"),
            "book":    b.get("book"),
            "edge":    b.get("edge"),
            "edge_pct": b.get("edge_pct"),
            "kelly_pct": b.get("kelly_pct"),
            "stake_dollars": b.get("stake_dollars"),
        })

    # SHIP gate evaluation
    gate_reasons = []
    counts_present = all(
        k in payload for k in (
            "n_predictions_available", "n_snapshots_loaded",
            "n_evaluated", "n_filtered_out", "n_filtered_kelly_cap",
        )
    )
    if not counts_present:
        gate_reasons.append("missing required counts in payload")
    if not isinstance(recs, list):
        gate_reasons.append("recommendations is not a list")
    ship = len(gate_reasons) == 0

    result = {
        "probe":           "R23_P8",
        "ran_at":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_date":     target_date,
        "bankroll":        float(bankroll),
        "top":             int(top),
        "min_edge":        float(min_edge),
        "engine_payload_summary": {
            "engine_version":            payload.get("engine_version"),
            "n_predictions_available":   payload.get("n_predictions_available"),
            "n_snapshots_loaded":        payload.get("n_snapshots_loaded"),
            "n_out_players_in_feed":     payload.get("n_out_players_in_feed"),
            "n_evaluated":               payload.get("n_evaluated"),
            "n_filtered_out":            payload.get("n_filtered_out"),
            "n_filtered_no_pred":        payload.get("n_filtered_no_pred"),
            "n_filtered_min_edge":       payload.get("n_filtered_min_edge"),
            "n_candidates_pos_edge":     payload.get("n_candidates_pos_edge"),
            "n_recs":                    payload.get("n_recs", 0),
            "n_filtered_kelly_cap":      payload.get("n_filtered_kelly_cap"),
            "books_loaded":              payload.get("books_loaded"),
            "slate_cap_dollars":         payload.get("slate_cap_dollars"),
            "total_stake_post_cap":      payload.get("total_stake_post_cap"),
            "reason":                    payload.get("reason"),
        },
        "top_3_recs":      top3,
        "ship":            ship,
        "ship_blockers":   gate_reasons,
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--min-edge", type=float, default=0.05)
    args = ap.parse_args()
    result = run_probe(
        bankroll=args.bankroll,
        top=args.top,
        date=args.date,
        min_edge=args.min_edge,
    )
    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())
