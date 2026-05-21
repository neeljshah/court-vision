"""snapshot_clv.py — Daily CLV snapshot CLI.

Loads bets from the data lake (data/models/bet_log.json + clv_log.json),
joins to closing lines, and writes one JSON file per day to data/clv/.

Usage
-----
    python scripts/snapshot_clv.py                        # today
    python scripts/snapshot_clv.py --date 2026-05-20     # specific date
    python scripts/snapshot_clv.py --all                  # all dates in log
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# Allow running from repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.validation.clv_tracker import OddsFormat, compute_clv

# ── paths ─────────────────────────────────────────────────────────────────────

_BET_LOG  = os.path.join(_ROOT, "data", "models", "bet_log.json")
_CLV_LOG  = os.path.join(_ROOT, "data", "models", "clv_log.json")
_OUT_DIR  = os.path.join(_ROOT, "data", "clv")

_SNAPSHOT_SCHEMA = {
    "bet_id":        str,
    "taken_odds":    float,
    "closing_odds":  float,
    "clv_pct":       float,
    "ev_delta_usd":  float,
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_json(path: str) -> Any:
    """Load JSON file; return [] on missing or corrupt."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_snapshot(day: str, rows: List[Dict[str, Any]]) -> str:
    """Write rows to data/clv/<day>.json. Returns output path."""
    os.makedirs(_OUT_DIR, exist_ok=True)
    out_path = os.path.join(_OUT_DIR, f"{day}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return out_path


# ── core logic ────────────────────────────────────────────────────────────────

def _detect_fmt(odds: Any) -> OddsFormat:
    """Guess odds format from value."""
    if isinstance(odds, float) and 0.0 < odds < 1.0:
        return "prob"
    if isinstance(odds, (int, float)) and 1.0 < odds < 30.0:
        return "decimal"
    return "american"


def build_snapshot(
    bets: List[Dict[str, Any]],
    clv_entries: List[Dict[str, Any]],
    target_date: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Join bets to closing lines and compute CLV.

    Parameters
    ----------
    bets:
        Records from bet_log.json. Expected fields: bet_id, stake,
        taken_odds (or opening_line), placed_at (ISO datetime).
    clv_entries:
        Records from clv_log.json. Expected fields: bet_id, closing_line.
    target_date:
        YYYY-MM-DD filter. None = include all dates.

    Returns
    -------
    dict
        Mapping of date string → list of snapshot rows.
    """
    closing_map: Dict[str, float] = {}
    for entry in clv_entries:
        bid = entry.get("bet_id", "")
        cl  = entry.get("closing_line")
        if bid and cl is not None:
            closing_map[bid] = float(cl)

    by_date: Dict[str, List[Dict[str, Any]]] = {}

    for bet in bets:
        bet_id = str(bet.get("bet_id", ""))
        if not bet_id:
            continue

        # Extract placement date
        placed_raw = bet.get("placed_at") or bet.get("timestamp") or ""
        try:
            day = datetime.fromisoformat(str(placed_raw)).date().isoformat()
        except (ValueError, TypeError):
            day = date.today().isoformat()

        if target_date and day != target_date:
            continue

        # Odds fields — support multiple naming conventions
        taken_odds_raw = (
            bet.get("taken_odds")
            or bet.get("opening_line")
            or bet.get("odds")
        )
        if taken_odds_raw is None:
            continue

        closing_odds_raw = closing_map.get(bet_id)
        if closing_odds_raw is None:
            # closing line embedded in bet record
            closing_odds_raw = bet.get("closing_line") or bet.get("closing_odds")
        if closing_odds_raw is None:
            continue

        stake = float(bet.get("stake", 0.0))
        if stake <= 0:
            stake = 100.0  # default $100 unit if not recorded

        taken_odds  = float(taken_odds_raw)
        closing_odds = float(closing_odds_raw)
        fmt = _detect_fmt(taken_odds)

        try:
            result = compute_clv(taken_odds, closing_odds, stake, fmt=fmt)
        except (ValueError, ZeroDivisionError):
            continue

        row: Dict[str, Any] = {
            "bet_id":       bet_id,
            "taken_odds":   taken_odds,
            "closing_odds": closing_odds,
            "clv_pct":      result.clv_pct,
            "ev_delta_usd": result.ev_delta_usd,
        }
        by_date.setdefault(day, []).append(row)

    return by_date


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Write daily CLV snapshots to data/clv/")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--date", metavar="YYYY-MM-DD",
                       help="Process a specific date (default: today)")
    group.add_argument("--all", action="store_true",
                       help="Process all dates found in bet_log.json")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    bets        = _load_json(_BET_LOG)
    clv_entries = _load_json(_CLV_LOG)

    if not isinstance(bets, list):
        bets = []
    if not isinstance(clv_entries, list):
        clv_entries = []

    target_date: Optional[str] = None
    if not args.all:
        target_date = args.date or date.today().isoformat()

    snapshots = build_snapshot(bets, clv_entries, target_date=target_date)

    if not snapshots:
        print(f"No CLV data for {target_date or 'any date'}. "
              f"Checked {len(bets)} bets, {len(clv_entries)} CLV entries.")
        sys.exit(0)

    for day, rows in sorted(snapshots.items()):
        out = _save_snapshot(day, rows)
        total_ev = sum(r["ev_delta_usd"] for r in rows)
        avg_clv  = sum(r["clv_pct"] for r in rows) / len(rows)
        print(f"{day}: {len(rows)} bets | avg CLV {avg_clv:+.2f}% | "
              f"total EV ${total_ev:+.2f} → {out}")


if __name__ == "__main__":
    main()
