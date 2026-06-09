"""build_props_from_lines.py — INT-96A FIX #2: Props JSON adapter from lines CSVs.

Reads data/lines/<date>_*.csv (skips snapshots/ subdirs and *_inplay.csv),
consolidates per-book rows into one canonical (player_name, stat) row per pair
using median line + best odds, and writes data/props/props_<date>.json matching
the schema consumed by _load_props in build_daily_slate.py (INT-85).

Usage:
    python scripts/build_props_from_lines.py --date 2026-05-29
    python scripts/build_props_from_lines.py  # defaults to today
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

# ── bootstrap path ────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_LINES_DIR = os.path.join(ROOT, "data", "lines")
_PROPS_DIR = os.path.join(ROOT, "data", "props")

# Stat name normalisation map (book → canonical INT-85 stat name)
_STAT_NORM: Dict[str, str] = {
    "pts": "pts",
    "points": "pts",
    "point": "pts",
    "reb": "reb",
    "rebounds": "reb",
    "rebound": "reb",
    "ast": "ast",
    "assists": "ast",
    "assist": "ast",
    "fg3m": "fg3m",
    "3pm": "fg3m",
    "threes": "fg3m",
    "3-pt made": "fg3m",
    "3 pt made": "fg3m",
    "3 point made": "fg3m",
    "stl": "stl",
    "steals": "stl",
    "steal": "stl",
    "blk": "blk",
    "blocks": "blk",
    "block": "blk",
    "tov": "tov",
    "turnovers": "tov",
    "turnover": "tov",
    "to": "tov",
}

VALID_STATS = frozenset(["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])


def _normalise_stat(raw: str) -> Optional[str]:
    """Map raw stat string to canonical stat key, or None if unrecognised."""
    key = str(raw).strip().lower()
    return _STAT_NORM.get(key)


def _safe_int(val) -> Optional[int]:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f else None  # exclude NaN
    except (ValueError, TypeError):
        return None


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def _best_over_odds(values: List[int]) -> int:
    """Best (highest) over odds — most favourable for bettor."""
    if not values:
        return -110
    return max(values)


def _best_under_odds(values: List[int]) -> int:
    """Best (highest) under odds."""
    if not values:
        return -110
    return max(values)


def load_lines_csvs(date_str: str) -> List[Dict]:
    """Return flat list of raw row dicts from all per-book CSVs for the date."""
    import csv

    pattern = os.path.join(_LINES_DIR, f"{date_str}_*.csv")
    files = glob.glob(pattern)
    # Exclude inplay files and files inside snapshots/ subdir
    files = [
        f for f in files
        if "_inplay" not in os.path.basename(f).lower()
        and "snapshots" not in f.replace("\\", "/")
    ]
    if not files:
        print(f"  [build_props] No CSV files matching {pattern} (excluding inplay/snapshots).")
        return []

    rows: List[Dict] = []
    for fpath in sorted(files):
        book = os.path.basename(fpath).replace(f"{date_str}_", "").replace(".csv", "")
        try:
            with open(fpath, encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    row["_book"] = book
                    rows.append(dict(row))
        except Exception as e:
            print(f"  [build_props] warn: skipping {fpath}: {e}")
    print(f"  [build_props] Read {len(rows)} raw rows from {len(files)} CSV(s).")
    return rows


def consolidate(raw_rows: List[Dict]) -> List[Dict]:
    """
    Group by (player_name, stat), aggregate across books:
    - line: median
    - over_odds: best (highest)
    - under_odds: best (highest)

    Returns list of dicts matching props JSON schema:
    {"player": str, "stat": str, "line": float, "over_odds": int, "under_odds": int}
    """
    # Per (player_name, stat) → accumulate lines + odds lists
    accum: Dict[Tuple[str, str], Dict] = {}
    skipped = 0
    name_failures: List[str] = []

    for row in raw_rows:
        # --- player name ---
        player_raw = (
            row.get("player_name") or row.get("player") or row.get("name") or ""
        ).strip()
        if not player_raw:
            skipped += 1
            continue

        # --- stat ---
        stat_raw = (row.get("stat") or row.get("market") or row.get("prop") or "").strip()
        stat = _normalise_stat(stat_raw)
        if stat is None:
            # Log first occurrence only to avoid flood
            if stat_raw not in name_failures:
                name_failures.append(stat_raw)
            skipped += 1
            continue

        # --- line ---
        line = _safe_float(row.get("line") or row.get("ou_line") or row.get("handicap"))
        if line is None:
            skipped += 1
            continue

        # --- odds ---
        over_odds = _safe_int(
            row.get("over_price") or row.get("over_odds") or row.get("over")
        )
        under_odds = _safe_int(
            row.get("under_price") or row.get("under_odds") or row.get("under")
        )
        if over_odds is None:
            over_odds = -110
        if under_odds is None:
            under_odds = -110

        key = (player_raw, stat)
        if key not in accum:
            accum[key] = {"lines": [], "over_odds": [], "under_odds": []}
        accum[key]["lines"].append(line)
        accum[key]["over_odds"].append(over_odds)
        accum[key]["under_odds"].append(under_odds)

    if name_failures:
        print(f"  [build_props] Unrecognised stat names (skipped): {name_failures[:10]}")
    print(f"  [build_props] Skipped {skipped} rows; consolidated {len(accum)} (player,stat) pairs.")

    result: List[Dict] = []
    for (player, stat), data in sorted(accum.items()):
        result.append({
            "player":      player,
            "stat":        stat,
            "line":        round(_median(data["lines"]), 1),
            "over_odds":   _best_over_odds(data["over_odds"]),
            "under_odds":  _best_under_odds(data["under_odds"]),
        })

    return result


def write_props_json(props: List[Dict], date_str: str) -> str:
    """Atomically write props_<date>.json using tempfile + os.replace."""
    os.makedirs(_PROPS_DIR, exist_ok=True)
    out_path = os.path.join(_PROPS_DIR, f"props_{date_str}.json")

    # Atomic write: write to temp then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=_PROPS_DIR, prefix=f"props_{date_str}_", suffix=".tmp.json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(props, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return out_path


def build_props(date_str: str) -> int:
    """Main entry point. Returns number of props written."""
    print(f"\n  [build_props] Building props JSON for {date_str}...")

    raw_rows = load_lines_csvs(date_str)
    if not raw_rows:
        # Stub graceful empty file so build_daily_slate.py loads cleanly
        out_path = write_props_json([], date_str)
        print(f"  [build_props] No rows found — wrote empty stub: {out_path}")
        return 0

    props = consolidate(raw_rows)
    if not props:
        out_path = write_props_json([], date_str)
        print(f"  [build_props] Consolidation produced 0 rows — wrote empty stub.")
        return 0

    out_path = write_props_json(props, date_str)
    print(f"  [build_props] Wrote {len(props)} props to: {out_path}")

    # Sample first 3 for verification
    print(f"  [build_props] Sample (first 3):")
    for p in props[:3]:
        print(f"    {p['player']:30s}  {p['stat']:5s}  line={p['line']:.1f}  "
              f"over={p['over_odds']:+d}  under={p['under_odds']:+d}")

    return len(props)


def main() -> int:
    ap = argparse.ArgumentParser(description="INT-96A FIX #2: Build props JSON from lines CSVs")
    ap.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    date_str = args.date or _date.today().isoformat()
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"  [fail] bad --date '{date_str}' — use YYYY-MM-DD")
        return 2

    n = build_props(date_str)
    print(f"\n  [build_props] Done. {n} props written for {date_str}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
