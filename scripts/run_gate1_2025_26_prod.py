"""Gate 1 vs REAL Vegas (2025-26) — using ACTUAL prod-stack OOF predictions.

Same data as run_gate1_2025_26.py (benashkar/nba_gambling DK/FD/MGM closes)
but uses data/cache/pregame_oof.parquet — the walk-forward OUT-OF-SAMPLE
predictions from the production model stack. This is the honest test of
the prod system vs real DK/FD/MGM closing lines on the 2025-26 season.

Walk-forward guarantee: every OOF prediction was made by a model trained
ONLY on data prior to that game_date. No peeking.
"""
from __future__ import annotations

import csv
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_SNAPS_DIR = _ROOT / "data" / "external" / "historical_lines" / "benashkar_nba_gambling"
_NBA_DIR = _ROOT / "data" / "nba"
_OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
_OUT = _ROOT / "data" / "cache" / "gate1_2025_26_prod_results.json"

PROP_TO_STAT: Dict[str, str] = {
    "points": "pts",
    "rebounds": "reb",
    "assists": "ast",
    "threes": "fg3m",
    "steals": "stl",
    "blocks": "blk",
    "turnovers": "tov",
}
KEEP_BOOKS = {"draftkings", "fanduel", "betmgm"}


def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _payout(odds: float, win: bool) -> float:
    if not win:
        return -100.0
    if odds < 0:
        return 100.0 / abs(odds) * 100.0
    return odds / 100.0 * 100.0


def _build_name_to_pid() -> Dict[str, int]:
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
                out[name_lc.strip().lower()] = int(pid)
    return out


def main() -> int:
    files = sorted(glob.glob(str(_SNAPS_DIR / "data__output__player_props_*.csv")))
    if not files:
        print(f"ERROR: no snapshots in {_SNAPS_DIR}")
        return 1
    print(f"Loading {len(files)} snapshot files...")

    # Keep latest scrape per (player, game_date, book, prop, line) — closing proxy
    latest: Dict[Tuple[str, str, str, str, float], dict] = {}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                book = (row.get("sportsbook") or "").lower()
                if book not in KEEP_BOOKS:
                    continue
                if row.get("is_alt_line", "").lower() == "true":
                    continue
                prop = (row.get("prop_type") or "").lower()
                if prop not in PROP_TO_STAT:
                    continue
                try:
                    line = float(row.get("line") or 0)
                    over_odds = float(row.get("over_odds") or 0)
                    under_odds = float(row.get("under_odds") or 0)
                except (ValueError, TypeError):
                    continue
                if over_odds == 0 or under_odds == 0:
                    continue
                player = (row.get("player_name") or "").strip().lower()
                gdate = (row.get("game_date") or "").strip()
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
    print(f"  unique closing rows: {len(latest):,}")

    # Load OOF predictions
    print(f"Loading OOF parquet {_OOF.relative_to(_ROOT)}...")
    oof = pd.read_parquet(_OOF)
    oof["game_date"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    print(f"  OOF rows: {len(oof):,}  date range: {oof['game_date'].min()} .. {oof['game_date'].max()}")

    # Index OOF for fast lookup: (player_id, game_date, stat) -> oof_pred + actual
    oof_idx = {}
    for r in oof.itertuples(index=False):
        key = (int(r.player_id), r.game_date, r.stat)
        oof_idx[key] = (float(r.oof_pred), float(r.actual))
    print(f"  OOF index: {len(oof_idx):,} entries")

    name_to_pid = _build_name_to_pid()
    print(f"  name -> pid map: {len(name_to_pid):,}")

    n_props = 0
    n_unmatched_name = 0
    n_no_oof = 0
    n_push = 0
    n_bets = 0
    n_wins = 0
    total_pnl = 0.0
    by_stat: Dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    by_book: Dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})

    for rec in latest.values():
        n_props += 1
        stat = PROP_TO_STAT.get(rec["prop"])
        if stat is None:
            continue
        pid = name_to_pid.get(rec["player"])
        if pid is None:
            n_unmatched_name += 1
            continue

        key = (pid, rec["game_date"], stat)
        oof_entry = oof_idx.get(key)
        if oof_entry is None:
            n_no_oof += 1
            continue
        predicted, actual = oof_entry

        line = rec["line"]
        if abs(predicted - line) < 1e-9:
            continue
        bet_over = predicted > line

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
    print("=== Gate 1: REAL Vegas (2025-26) — PROD-STACK walk-forward OOF ===")
    print(f"  Lines:     benashkar/nba_gambling (DK/FD/MGM, Jan-May 2026)")
    print(f"  Predictor: pregame_oof.parquet (production model stack, walk-forward OOF)")
    print()
    print(f"closing rows scanned: {n_props:,}")
    print(f"  unmatched name:     {n_unmatched_name:,}")
    print(f"  no OOF prediction:  {n_no_oof:,}")
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
    print(f"total_pnl: ${total_pnl:,.2f} on ${n_bets * 100:,.2f} staked")
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

    out = {
        "n_bets": n_bets,
        "n_wins": n_wins,
        "beat_rate": beat,
        "roi_pct": roi,
        "total_pnl": total_pnl,
        "by_stat": {k: dict(v) for k, v in by_stat.items()},
        "by_book": {k: dict(v) for k, v in by_book.items()},
        "data_source": "benashkar/nba_gambling (DK/FD/MGM) vs pregame_oof.parquet (prod stack WF)",
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(_OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nResults: {_OUT.relative_to(_ROOT)}")

    passed = beat >= 0.55 and roi >= 3.0
    print(f"\nGate 1 (2025-26 prod stack): {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
