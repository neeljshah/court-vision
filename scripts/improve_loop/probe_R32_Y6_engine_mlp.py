"""probe_R32_Y6_engine_mlp.py — viability probe for R32_Y6.

Runs the R23_P8 live recommendation engine twice — once with
``M2_FAMILY_USE_MLP=0`` (multi5 ensemble) and once with
``M2_FAMILY_USE_MLP=1`` (R31_X3 multitask MLP) — against TODAY's real data
(falls back to the most recent date with both a predictions cache and at
least one book snapshot, up to 7 days back).

Quantifies whether the operator would have placed DIFFERENT bets with the
MLP active. Persists the result so the operator dashboard can surface the
mode-compare summary without re-running the engine.

SHIP gate
---------
  * comparison runs end-to-end without raising
  * both modes return well-formed payloads (recommendations is a list)
  * counts present: jaccard_top_5, jaccard_top_10, jaccard_top_20

Persists:
  data/cache/probe_R32_Y6_results.json
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

from scripts.compare_engine_modes import compare_modes  # noqa: E402

_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R32_Y6_results.json"
)


def _has_data_for(date_str: str) -> bool:
    """Same data-availability guard as probe_R23_P8."""
    preds = os.path.join(
        PROJECT_DIR, "data", "cache", f"predictions_cache_{date_str}.parquet"
    )
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
    top: int = 20,
    date: Optional[str] = None,
    min_edge: float = 0.03,
) -> Dict[str, Any]:
    target_date = _pick_target_date(date)
    cmp_payload = compare_modes(
        bankroll=bankroll,
        top=top,
        date=target_date,
        min_edge=min_edge,
        top_overlap_k=(5, 10, 20),
    )

    overlap = cmp_payload.get("overlap", {}) or {}
    shared = cmp_payload.get("shared_bets", {}) or {}
    top_3_changes = []
    for b in cmp_payload.get("only_in_mlp", [])[:3]:
        top_3_changes.append({
            "kind": "added_by_mlp",
            "player": b.get("player"), "stat": b.get("stat"),
            "side":   b.get("side"),   "book": b.get("book"),
            "line":   b.get("line"),   "edge_pct": b.get("edge_pct"),
            "stake_dollars": b.get("stake_dollars"),
        })
    for b in cmp_payload.get("only_in_multi5", [])[:3]:
        top_3_changes.append({
            "kind": "dropped_by_mlp",
            "player": b.get("player"), "stat": b.get("stat"),
            "side":   b.get("side"),   "book": b.get("book"),
            "line":   b.get("line"),   "edge_pct": b.get("edge_pct"),
            "stake_dollars": b.get("stake_dollars"),
        })

    gate_reasons = []
    needed = {"top_5", "top_10", "top_20"}
    if not needed.issubset(overlap.keys()):
        gate_reasons.append(f"missing overlap buckets: {needed - overlap.keys()}")
    if not isinstance(cmp_payload.get("top_multi5"), list):
        gate_reasons.append("top_multi5 is not a list")
    if not isinstance(cmp_payload.get("top_mlp"), list):
        gate_reasons.append("top_mlp is not a list")

    ship = len(gate_reasons) == 0

    result = {
        "probe":          "R32_Y6",
        "ran_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_date":    target_date,
        "bankroll":       float(bankroll),
        "top":            int(top),
        "min_edge":       float(min_edge),
        "n_recs_multi5":  cmp_payload.get("multi5", {}).get("n_recs", 0),
        "n_recs_mlp":     cmp_payload.get("mlp", {}).get("n_recs", 0),
        "jaccard_top_5":  overlap.get("top_5", {}).get("jaccard"),
        "jaccard_top_10": overlap.get("top_10", {}).get("jaccard"),
        "jaccard_top_20": overlap.get("top_20", {}).get("jaccard"),
        "n_shared":              shared.get("n_shared", 0),
        "mean_abs_edge_delta":   shared.get("mean_abs_edge_delta", 0.0),
        "total_abs_stake_delta": shared.get("total_abs_stake_delta", 0.0),
        "n_only_in_multi5":      len(cmp_payload.get("only_in_multi5", [])),
        "n_only_in_mlp":         len(cmp_payload.get("only_in_mlp", [])),
        "operator_would_change_bets": cmp_payload.get(
            "operator_would_change_bets", False
        ),
        "top_3_changes":   top_3_changes,
        "ship":            ship,
        "ship_blockers":   gate_reasons,
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--min-edge", type=float, default=0.03)
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
