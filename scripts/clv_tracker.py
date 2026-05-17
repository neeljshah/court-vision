"""
clv_tracker.py — Fetch, store, and analyze Closing Line Value (CLV).

Tracks realized CLV vs model opening lines for each bet, persists to
data/models/clv_log.json, and produces per-stat CLV summaries.

Public API
----------
    update_clv_log(entries, log_path)  -> None
    get_clv_summary(log_path)          -> dict
    fetch_closing_lines(bets)          -> list[dict]  (stub — requires odds feed)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

_DEFAULT_LOG = PROJECT_DIR / "data" / "models" / "clv_log.json"


def _compute_clv(entry: dict) -> float:
    """CLV = signed line movement in the direction we bet.

    Over bet:  positive CLV when closing_line > opening_line (line moved up, good for us).
    Under bet: positive CLV when closing_line < opening_line (line moved down, good for us).
    """
    opening = float(entry.get("opening_line", 0.0))
    closing = float(entry.get("closing_line", opening))
    direction = str(entry.get("direction", "over")).lower()
    if opening <= 0:
        return 0.0
    if direction == "over":
        return round((closing - opening) / opening, 4)
    else:
        return round((opening - closing) / opening, 4)


def update_clv_log(
    entries: List[Dict],
    log_path: Optional[str] = None,
) -> None:
    """
    Compute realized CLV for each entry and append to the persistent log.

    Each entry dict must have:
        bet_id, stat, direction, opening_line, closing_line, edge_pct (optional)

    Writes merged log to log_path (default: data/models/clv_log.json).
    Skips duplicates by bet_id.
    """
    path = Path(log_path) if log_path else _DEFAULT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: List[Dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_ids = {e.get("bet_id") for e in existing}
    added = 0
    for entry in entries:
        bet_id = entry.get("bet_id")
        if bet_id in existing_ids:
            continue
        enriched = dict(entry)
        enriched["clv"] = _compute_clv(entry)
        existing.append(enriched)
        existing_ids.add(bet_id)
        added += 1

    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  [clv_tracker] +{added} entries ({len(existing)} total) -> {path}")


def get_clv_summary(log_path: Optional[str] = None) -> Dict:
    """
    Compute per-stat and overall CLV summary from the log.

    Returns:
        {
            "n_bets": int,
            "mean_clv": float,
            "pct_positive": float,  # fraction with clv > 0
            "by_stat": {stat: {mean_clv, n, pct_positive}},
        }
    """
    path = Path(log_path) if log_path else _DEFAULT_LOG
    if not path.exists():
        return {"n_bets": 0, "mean_clv": 0.0, "pct_positive": 0.0, "by_stat": {}}

    try:
        data: List[Dict] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"n_bets": 0, "mean_clv": 0.0, "pct_positive": 0.0, "by_stat": {}}

    clv_vals = [float(e["clv"]) for e in data if "clv" in e]
    if not clv_vals:
        return {"n_bets": 0, "mean_clv": 0.0, "pct_positive": 0.0, "by_stat": {}}

    by_stat: Dict[str, List[float]] = {}
    for e in data:
        if "clv" not in e:
            continue
        stat = str(e.get("stat", "unknown"))
        by_stat.setdefault(stat, []).append(float(e["clv"]))

    stat_summary = {}
    for stat, vals in by_stat.items():
        stat_summary[stat] = {
            "mean_clv": round(sum(vals) / len(vals), 4),
            "n": len(vals),
            "pct_positive": round(sum(1 for v in vals if v > 0) / len(vals), 3),
        }

    return {
        "n_bets": len(clv_vals),
        "mean_clv": round(sum(clv_vals) / len(clv_vals), 4),
        "pct_positive": round(sum(1 for v in clv_vals if v > 0) / len(clv_vals), 3),
        "by_stat": stat_summary,
    }


def fetch_closing_lines(bets: List[Dict]) -> List[Dict]:
    """
    Fetch closing lines for open bets from the odds data source.

    Stub implementation — returns bets with closing_line=None until an
    odds API is wired in (Phase 11). Callers should check for None.
    """
    updated = []
    for bet in bets:
        enriched = dict(bet)
        if enriched.get("closing_line") is None:
            enriched["closing_line"] = None  # placeholder for real fetch
        updated.append(enriched)
    return updated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CLV tracker")
    parser.add_argument("--summary", action="store_true", help="Print CLV summary")
    args = parser.parse_args()

    if args.summary:
        summary = get_clv_summary()
        print(f"CLV Summary: {json.dumps(summary, indent=2)}")
