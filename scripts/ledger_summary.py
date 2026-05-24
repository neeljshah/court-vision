"""ledger_summary.py — summary view over the accumulated predictions ledger.

Cycles 47 + 49 wired predict_slate and predict_player to append every
prediction to data/predictions/<date>.csv (shared schema). Over time this
becomes the historical record we'll join with actuals + closing lines for
the cycle-52 honest backtest. This script gives ops a quick read of what
the model said over a date range.

Schema (one row per (player, stat)):
    date, game_id, player_id, player, team, opp, venue, stat, pred

Run:
    python scripts/ledger_summary.py                              # last 7 days
    python scripts/ledger_summary.py --start 2026-05-01 --end 2026-05-24
    python scripts/ledger_summary.py --player "Nikola Jokic"      # one player history
    python scripts/ledger_summary.py --stat pts --top 20          # top-20 PTS predictions
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import date as _date, timedelta
from typing import List, Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")


def list_ledger_files(start: Optional[_date] = None,
                       end: Optional[_date] = None,
                       pred_dir: Optional[str] = None) -> List[str]:
    """Return ledger CSV paths within [start, end] (inclusive). Default: last 7d."""
    pred_dir = pred_dir or _PRED_DIR
    if not os.path.isdir(pred_dir):
        return []
    if end is None:
        end = _date.today()
    if start is None:
        start = end - timedelta(days=6)
    out: List[str] = []
    for path in sorted(glob.glob(os.path.join(pred_dir, "*.csv"))):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            d = _date.fromisoformat(name)
        except ValueError:
            continue
        if start <= d <= end:
            out.append(path)
    return out


def load_rows(paths: List[str]) -> List[Dict[str, str]]:
    """Read all CSVs into a single list. Missing files silently skipped."""
    rows: List[Dict[str, str]] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                rows.extend(csv.DictReader(fh))
        except (OSError, csv.Error):
            continue
    return rows


def summarize(rows: List[Dict[str, str]],
              player: Optional[str] = None,
              stat: Optional[str] = None,
              top: int = 10) -> dict:
    """Filter + aggregate rows into the summary dict the CLI prints."""
    # Filter
    if player:
        key = player.strip().lower()
        rows = [r for r in rows if r.get("player", "").strip().lower() == key]
    if stat:
        rows = [r for r in rows if r.get("stat", "") == stat.lower()]

    # Coerce
    parsed = []
    for r in rows:
        try:
            pred = float(r["pred"])
        except (KeyError, ValueError):
            continue
        parsed.append({**r, "pred_f": pred})

    by_player: Dict[str, int] = defaultdict(int)
    by_stat: Dict[str, List[float]] = defaultdict(list)
    dates = set()
    for r in parsed:
        by_player[r.get("player", "")] += 1
        by_stat[r.get("stat", "")].append(r["pred_f"])
        dates.add(r.get("date", ""))

    # Top-N by predicted value (within the filtered slice).
    top_rows = sorted(parsed, key=lambda r: r["pred_f"], reverse=True)[:top]

    return {
        "n_rows": len(parsed),
        "n_dates": len(dates),
        "n_players": len(by_player),
        "by_stat_mean": {s: (sum(v) / len(v)) for s, v in by_stat.items() if v},
        "by_stat_count": {s: len(v) for s, v in by_stat.items()},
        "top_predicted_players": sorted(by_player.items(),
                                         key=lambda kv: kv[1],
                                         reverse=True)[:top],
        "top_rows": top_rows,
    }


def _print_summary(s: dict, top: int) -> None:
    print(f"\nLedger covers {s['n_dates']} date(s) | "
          f"{s['n_rows']} prediction rows | "
          f"{s['n_players']} unique players")
    if s["by_stat_mean"]:
        print("\nMean prediction per stat:")
        for st in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            if st in s["by_stat_mean"]:
                print(f"  {st.upper():4s}  mean {s['by_stat_mean'][st]:>6.2f}  "
                      f"n={s['by_stat_count'][st]}")
    if s["top_predicted_players"]:
        print(f"\nMost-predicted players (top {top}):")
        for p, n in s["top_predicted_players"]:
            print(f"  {n:>4d}  {p}")
    if s["top_rows"]:
        print(f"\nTop {len(s['top_rows'])} predictions by value:")
        for r in s["top_rows"]:
            print(f"  {r['date']}  {r['player']:<22s} {r['stat'].upper():4s} "
                  f"{r['pred_f']:>6.2f}  vs {r.get('opp', ''):<3s} ({r.get('venue', '')})")


def main() -> int:
    ap = argparse.ArgumentParser(description="NBA prediction ledger summary")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default: 7 days ago)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--player", default=None, help="filter to one player (case-insensitive)")
    ap.add_argument("--stat", default=None, choices=["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
    ap.add_argument("--top", type=int, default=10, help="top-N for ranked sections")
    args = ap.parse_args()

    start = _date.fromisoformat(args.start) if args.start else None
    end = _date.fromisoformat(args.end) if args.end else None
    paths = list_ledger_files(start, end)
    if not paths:
        print(f"  [empty] no predictions ledger files in {_PRED_DIR}")
        print("          run scripts/predict_slate.py --save or "
              "scripts/predict_player.py ... --save first.")
        return 1
    rows = load_rows(paths)
    s = summarize(rows, player=args.player, stat=args.stat, top=args.top)
    _print_summary(s, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
