"""Gate 1 against REAL Vegas closes — 2024 NBA playoffs.

Uses data/external/historical_lines/playoffs_2024_canonical.csv (5,109 rows
of DK/FD/MGM/BetRivers closing lines + actual outcomes from the 2024
playoffs, Apr 21 - May 24, 2024) and scores an L10 rolling-average baseline
predictor against it.

The baseline = the same model the historical residuals builder uses. NOT
the full prod stack (which can't be reanimated for arbitrary historical
(player, date) tuples without setting up the full feature pipeline). So
this is a LOWER BOUND on prod-stack performance — if the L10 baseline
already beats Vegas at the gate thresholds, prod is comfortably better.

Output: beat rate, ROI, per-stat breakdown. Real DK/FD/MGM/BetRivers,
real outcomes, real Vegas.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_CSV = _ROOT / "data" / "external" / "historical_lines" / "playoffs_2024_canonical.csv"
_AVGS_24_25 = _ROOT / "data" / "nba" / "player_avgs_2024-25.json"
_NBA_DIR = _ROOT / "data" / "nba"

STAT_COLS = {"pts": "PTS", "reb": "REB", "ast": "AST",
             "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}


def _parse_csv_date(s: str) -> str:
    """CSV uses ISO 'YYYY-MM-DD'; return unchanged."""
    return s.strip()


def _parse_gamelog_date(s: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _payout(odds: float, win: bool) -> float:
    """Dollar payout for a $100 stake."""
    if win:
        if odds < 0:
            return 100.0 / abs(odds) * 100.0
        return odds / 100.0 * 100.0
    return -100.0


def _build_name_to_pid() -> Dict[str, int]:
    """Lowercase player_name → player_id from player_avgs_2024-25.json.

    The 2024 playoffs follow the 2023-24 regular season but the player_avgs
    file for 2024-25 has the same player set with more current player_ids.
    The reisneriv dataset has names; we lowercase + strip for matching.
    """
    with open(_AVGS_24_25, encoding="utf-8") as fh:
        data = json.load(fh)
    out: Dict[str, int] = {}
    for name_lc, info in data.items():
        pid = info.get("player_id")
        if pid is None:
            continue
        out[name_lc.strip().lower()] = int(pid)
    return out


def _load_gamelog_rolling(pid: int, season: str = "2023-24") -> Optional[List[dict]]:
    """Load and date-sort one player's regular-season gamelog (ascending)."""
    path = _NBA_DIR / f"gamelog_{pid}_{season}.json"
    if not path.exists():
        return None
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    # Sort ascending by date so rows[:i] is history before game i
    keyed = []
    for r in rows:
        d = _parse_gamelog_date(r.get("GAME_DATE", ""))
        if d is None:
            continue
        keyed.append((d, r))
    keyed.sort(key=lambda kv: kv[0])
    return [r for _, r in keyed]


def _predict_l10(rows: List[dict], cutoff_date: datetime, stat: str) -> Optional[float]:
    """L10 (last 10) regular-season-game average for `stat` BEFORE cutoff_date."""
    col = STAT_COLS.get(stat)
    if col is None:
        return None
    history: List[float] = []
    for r in rows:
        d = _parse_gamelog_date(r.get("GAME_DATE", ""))
        if d is None or d >= cutoff_date:
            continue
        v = r.get(col)
        if v is None:
            continue
        try:
            history.append(float(v))
        except (TypeError, ValueError):
            continue
    if len(history) < 5:  # need at least 5 prior games
        return None
    last_10 = history[-10:]
    return sum(last_10) / len(last_10)


def main() -> int:
    if not _CSV.exists():
        print(f"ERROR: {_CSV} not found")
        return 1

    name_to_pid = _build_name_to_pid()

    # Cache: pid -> sorted gamelog rows
    gamelog_cache: Dict[int, Optional[List[dict]]] = {}

    n_lines = 0
    n_matched = 0
    n_unmatched_name = 0
    n_no_gamelog = 0
    n_no_pred = 0
    n_push = 0
    n_bets = 0
    n_wins = 0
    total_payout = 0.0
    by_stat: Dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})

    # Read CSV with replace on decode errors (some bytes are mojibake)
    with open(_CSV, encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n_lines += 1
            name = (row.get("player") or "").strip().lower()
            stat = (row.get("stat") or "").strip().lower()
            if stat not in STAT_COLS:
                continue
            date_iso = _parse_csv_date(row.get("date") or "")
            try:
                close_line = float(row.get("closing_line") or 0)
                actual = float(row.get("actual_value") or 0)
                over_odds = float(row.get("over_odds") or -110)
                under_odds = float(row.get("under_odds") or -110)
            except (ValueError, TypeError):
                continue

            pid = name_to_pid.get(name)
            if pid is None:
                n_unmatched_name += 1
                continue

            if pid not in gamelog_cache:
                gamelog_cache[pid] = _load_gamelog_rolling(pid)
            rows = gamelog_cache[pid]
            if rows is None:
                n_no_gamelog += 1
                continue

            cutoff = _parse_gamelog_date(date_iso)
            if cutoff is None:
                continue

            predicted = _predict_l10(rows, cutoff, stat)
            if predicted is None:
                n_no_pred += 1
                continue

            n_matched += 1

            # Determine bet direction
            if abs(predicted - close_line) < 1e-9:
                continue  # no edge → skip

            bet_over = predicted > close_line

            # Determine result
            if abs(actual - close_line) < 1e-9:
                n_push += 1
                continue
            won = (bet_over and actual > close_line) or (not bet_over and actual < close_line)

            odds = over_odds if bet_over else under_odds
            pnl = _payout(odds, won)

            n_bets += 1
            if won:
                n_wins += 1
            total_payout += pnl
            agg = by_stat[stat]
            agg["n"] += 1
            if won:
                agg["w"] += 1
            agg["pnl"] += pnl

    print("=== Gate 1: REAL Vegas (2024 NBA Playoffs, DK/FD/MGM/BetRivers) ===")
    print(f"  Source CSV:      {_CSV.relative_to(_ROOT)}")
    print(f"  Predictor:       L10 rolling avg from 2023-24 regular season gamelogs")
    print(f"  Date window:     2024-04-21 .. 2024-05-24 (playoffs)")
    print()
    print(f"CSV rows scanned:    {n_lines:,}")
    print(f"  unmatched name:    {n_unmatched_name:,}")
    print(f"  no gamelog:        {n_no_gamelog:,}")
    print(f"  no L10 prediction: {n_no_pred:,}")
    print(f"  matched:           {n_matched:,}")
    print(f"  pushes (skipped):  {n_push:,}")
    print(f"  resolved bets:     {n_bets:,}")
    print()

    if n_bets == 0:
        print("Gate 1 (REAL VEGAS): INSUFFICIENT DATA")
        return 1

    beat_rate = n_wins / n_bets
    roi = total_payout / (n_bets * 100.0) * 100.0
    print(f"beat_rate:  {beat_rate * 100.0:.2f}%  (need >=55%)")
    print(f"roi:        {roi:.2f}%  (need >=3%)")
    print(f"total_pnl:  ${total_payout:,.2f} on ${n_bets * 100:,.2f} staked ($100/bet)")
    print()
    print("Per-stat breakdown:")
    print(f"  {'stat':<6} {'n':>7} {'beat':>9} {'roi':>9}")
    for stat in sorted(by_stat):
        a = by_stat[stat]
        beat = a["w"] / a["n"] * 100.0 if a["n"] else 0.0
        sroi = a["pnl"] / (a["n"] * 100.0) * 100.0 if a["n"] else 0.0
        print(f"  {stat:<6} {a['n']:>7d} {beat:>8.2f}% {sroi:>8.2f}%")
    print()

    passed = beat_rate >= 0.55 and roi >= 3.0
    if passed:
        print("Gate 1 (REAL VEGAS): PASS")
        return 0
    print("Gate 1 (REAL VEGAS): FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
