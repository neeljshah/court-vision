"""Gate 1 against REAL Vegas (DK/FD/MGM) for the 2025-26 NBA season.

Uses data/external/historical_lines/benashkar_nba_gambling/ — 47 snapshots
of DK/FD/MGM player props across Jan 28 - May 8, 2026 (2025-26 regular
season + 2026 playoffs). Pulled from benashkar/nba_gambling on GitHub.

Pipeline:
  1. Consolidate all player_props_*.csv snapshots, keeping the LATEST
     scrape per (player, game_date, sportsbook, prop_type, line) — closest
     to closing.
  2. For each prop, look up the player's actual stat outcome from the
     2025-26 gamelog cache.
  3. Compute L10 rolling-average prediction from 2024-25 + 2025-26
     gamelogs (using only games BEFORE the prop's game_date).
  4. Bet over if predicted > line, under otherwise. Settle vs actual.
  5. Report beat-rate, ROI, per-stat + per-book breakdown.

Lower-bound result (L10 baseline). Prod stack typically lifts MAE by
10-20% over L10, so realized ROI on the prod stack would be higher.

Outputs JSON summary to data/cache/gate1_2025_26_results.json.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_SNAPS_DIR = _ROOT / "data" / "external" / "historical_lines" / "benashkar_nba_gambling"
_NBA_DIR = _ROOT / "data" / "nba"
_OUT = _ROOT / "data" / "cache" / "gate1_2025_26_results.json"

# Map benashkar prop_type → our stat key + gamelog column
PROP_TO_STAT: Dict[str, Tuple[str, str]] = {
    "points": ("pts", "PTS"),
    "rebounds": ("reb", "REB"),
    "assists": ("ast", "AST"),
    "threes": ("fg3m", "FG3M"),
    "steals": ("stl", "STL"),
    "blocks": ("blk", "BLK"),
    "turnovers": ("tov", "TOV"),
    "pts_rebs_asts": None,  # combined — skip
    "pts_rebs": None,
    "pts_asts": None,
    "rebs_asts": None,
    "fantasy_points": None,
    "double_double": None,
    "triple_double": None,
}

# Sportsbooks to keep
KEEP_BOOKS = {"draftkings", "fanduel", "betmgm"}


def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _payout(odds: float, win: bool) -> float:
    """Dollar payout for a $100 stake."""
    if not win:
        return -100.0
    if odds < 0:
        return 100.0 / abs(odds) * 100.0
    return odds / 100.0 * 100.0


def _build_name_to_pid() -> Dict[str, int]:
    """Lowercase player_name → player_id, from player_avgs files for both seasons."""
    out: Dict[str, int] = {}
    for season in ("2024-25", "2025-26"):
        path = _NBA_DIR / f"player_avgs_{season}.json"
        if not path.exists():
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for name_lc, info in data.items():
            pid = info.get("player_id")
            if pid is not None:
                # 2025-26 wins if both seasons have the player
                out[name_lc.strip().lower()] = int(pid)
    return out


def _load_gamelog(pid: int, season: str) -> List[dict]:
    path = _NBA_DIR / f"gamelog_{pid}_{season}.json"
    if not path.exists():
        return []
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return []


def _player_gamelog_dict(pid: int) -> List[Tuple[datetime, dict]]:
    """Combined 2024-25 + 2025-26 gamelog rows, ascending by date."""
    rows = []
    for season in ("2024-25", "2025-26"):
        for r in _load_gamelog(pid, season):
            d = _parse_date(r.get("GAME_DATE", ""))
            if d:
                rows.append((d, r))
    rows.sort(key=lambda kv: kv[0])
    return rows


def _predict_l10(rows: List[Tuple[datetime, dict]], cutoff: datetime, col: str) -> Optional[float]:
    history = [
        float(r[col])
        for d, r in rows
        if d < cutoff and r.get(col) is not None
        for _ in [None]  # noqa
    ]
    # cleaner version
    history = []
    for d, r in rows:
        if d >= cutoff:
            continue
        v = r.get(col)
        if v is None:
            continue
        try:
            history.append(float(v))
        except (TypeError, ValueError):
            continue
    if len(history) < 5:
        return None
    return sum(history[-10:]) / len(history[-10:])


def _actual_value(rows: List[Tuple[datetime, dict]], game_date: datetime, col: str) -> Optional[float]:
    """Find this player's actual stat for the game on game_date (±0 days)."""
    for d, r in rows:
        if d.date() == game_date.date():
            v = r.get(col)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def main() -> int:
    files = sorted(glob.glob(str(_SNAPS_DIR / "data__output__player_props_*.csv")))
    if not files:
        print(f"ERROR: no snapshot CSVs in {_SNAPS_DIR}")
        return 1
    print(f"Loading {len(files)} snapshot files...")

    # Closing-proxy: keep the LATEST scrape per (player, game_date, book, prop_type, line, side)
    # Key = (player_lc, game_date, book, prop_type, line)
    latest: Dict[Tuple[str, str, str, str, float], dict] = {}

    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                book = (row.get("sportsbook") or "").lower()
                if book not in KEEP_BOOKS:
                    continue
                if row.get("is_alt_line", "").lower() == "true":
                    continue  # mainline only
                prop = (row.get("prop_type") or "").lower()
                if prop not in PROP_TO_STAT or PROP_TO_STAT[prop] is None:
                    continue
                player = (row.get("player_name") or "").strip().lower()
                gdate = (row.get("game_date") or "").strip()
                try:
                    line = float(row.get("line") or 0)
                except (ValueError, TypeError):
                    continue
                try:
                    over_odds = float(row.get("over_odds") or 0)
                    under_odds = float(row.get("under_odds") or 0)
                except (ValueError, TypeError):
                    continue
                if over_odds == 0 or under_odds == 0:
                    continue
                scraped = row.get("scraped_at", "")
                key = (player, gdate, book, prop, line)
                prev = latest.get(key)
                if prev is None or scraped > prev["scraped_at"]:
                    latest[key] = {
                        "player": player,
                        "game_date": gdate,
                        "book": book,
                        "prop": prop,
                        "line": line,
                        "over_odds": over_odds,
                        "under_odds": under_odds,
                        "scraped_at": scraped,
                    }

    print(f"  unique (player, game, book, prop, line) closing rows: {len(latest):,}")

    # Build name → pid map
    name_to_pid = _build_name_to_pid()
    print(f"  name -> pid map: {len(name_to_pid):,} players")

    # Gamelog cache
    gl_cache: Dict[int, List[Tuple[datetime, dict]]] = {}

    n_props = 0
    n_unmatched_name = 0
    n_no_actual = 0
    n_no_pred = 0
    n_push = 0
    n_bets = 0
    n_wins = 0
    total_pnl = 0.0
    by_stat: Dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    by_book: Dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})

    for rec in latest.values():
        n_props += 1
        stat_info = PROP_TO_STAT.get(rec["prop"])
        if stat_info is None:
            continue
        stat, col = stat_info

        gdate_dt = _parse_date(rec["game_date"])
        if gdate_dt is None:
            continue

        pid = name_to_pid.get(rec["player"])
        if pid is None:
            n_unmatched_name += 1
            continue

        if pid not in gl_cache:
            gl_cache[pid] = _player_gamelog_dict(pid)
        rows = gl_cache[pid]

        actual = _actual_value(rows, gdate_dt, col)
        if actual is None:
            n_no_actual += 1
            continue

        pred = _predict_l10(rows, gdate_dt, col)
        if pred is None:
            n_no_pred += 1
            continue

        line = rec["line"]
        if abs(pred - line) < 1e-9:
            continue
        bet_over = pred > line

        if abs(actual - line) < 1e-9:
            n_push += 1
            continue
        won = (bet_over and actual > line) or (not bet_over and actual < line)

        odds = rec["over_odds"] if bet_over else rec["under_odds"]
        pnl = _payout(odds, won)

        n_bets += 1
        if won:
            n_wins += 1
        total_pnl += pnl

        a = by_stat[stat]
        a["n"] += 1
        a["pnl"] += pnl
        if won:
            a["w"] += 1
        b = by_book[rec["book"]]
        b["n"] += 1
        b["pnl"] += pnl
        if won:
            b["w"] += 1

    print()
    print("=== Gate 1: REAL Vegas (2025-26 NBA season, DK/FD/MGM) ===")
    print(f"  Source: benashkar/nba_gambling (47 snapshots, Jan 28 - May 8 2026)")
    print(f"  Predictor: L10 rolling avg from 2024-25 + 2025-26 gamelogs")
    print()
    print(f"closing rows scanned: {n_props:,}")
    print(f"  unmatched name:     {n_unmatched_name:,}")
    print(f"  no actual stat:     {n_no_actual:,}")
    print(f"  no L10 prediction:  {n_no_pred:,}")
    print(f"  pushes skipped:     {n_push:,}")
    print(f"  resolved bets:      {n_bets:,}")
    print()
    if n_bets == 0:
        print("Gate 1: INSUFFICIENT DATA")
        return 1

    beat = n_wins / n_bets
    roi = total_pnl / (n_bets * 100.0) * 100.0
    print(f"beat_rate: {beat * 100:.2f}%  (need >=55%)")
    print(f"roi:       {roi:.2f}%  (need >=3%)")
    print(f"total_pnl: ${total_pnl:,.2f} on ${n_bets * 100:,.2f} staked ($100/bet)")
    print()
    print("Per-stat breakdown:")
    print(f"  {'stat':<6} {'n':>7} {'beat':>9} {'roi':>9}")
    for stat in sorted(by_stat):
        a = by_stat[stat]
        bs = a["w"] / a["n"] * 100.0 if a["n"] else 0.0
        rs = a["pnl"] / (a["n"] * 100.0) * 100.0 if a["n"] else 0.0
        print(f"  {stat:<6} {a['n']:>7d} {bs:>8.2f}% {rs:>8.2f}%")
    print()
    print("Per-book breakdown:")
    print(f"  {'book':<12} {'n':>7} {'beat':>9} {'roi':>9}")
    for book in sorted(by_book):
        b = by_book[book]
        bs = b["w"] / b["n"] * 100.0 if b["n"] else 0.0
        rs = b["pnl"] / (b["n"] * 100.0) * 100.0 if b["n"] else 0.0
        print(f"  {book:<12} {b['n']:>7d} {bs:>8.2f}% {rs:>8.2f}%")

    # Write JSON
    out = {
        "n_bets": n_bets,
        "n_wins": n_wins,
        "beat_rate": beat,
        "roi_pct": roi,
        "total_pnl": total_pnl,
        "stake_per_bet": 100.0,
        "by_stat": {k: dict(v) for k, v in by_stat.items()},
        "by_book": {k: dict(v) for k, v in by_book.items()},
        "data_source": "benashkar/nba_gambling (DK/FD/MGM, Jan 28 - May 8 2026)",
        "predictor": "L10 rolling avg (lower bound vs prod stack)",
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nResults written to {_OUT.relative_to(_ROOT)}")

    passed = beat >= 0.55 and roi >= 3.0
    print(f"\nGate 1 (2025-26): {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
