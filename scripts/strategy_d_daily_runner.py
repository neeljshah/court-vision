"""strategy_d_daily_runner.py — operational daily runner for Strategy D.

Strategy D (iter-9 / iter-10 OOS finding): bet only BLK + FG3M + STL props at
flat $100 stake. Yielded +28.80% ROI / +$12,036 PnL / PnL-to-DD 38.94 — the
optimal risk-adjusted strategy from the OOS analysis. This script automates
running it daily by:

    1. Loading model predictions for the slate from
       data/cache/predictions_cache_<date>.parquet (q50 + bands per player/stat).
    2. Loading sportsbook lines from data/cache/probe_R15_tonight_slate_bets.json
       (or a fallback historical_lines path; degrades gracefully when no lines).
    3. Filtering to BLK / FG3M / STL only (the Strategy D filter).
    4. Computing edge = model_q50 - line; recommending OVER/UNDER if |edge|>0.5.
    5. Logging recommendations to data/bets/strategy_d_<date>.csv (dry-run).
    6. Printing a summary table grouped by stat.

Usage:
    python scripts/strategy_d_daily_runner.py --date 2026-05-27
    python scripts/strategy_d_daily_runner.py --game-id 0042500315 --bankroll 10000
    python scripts/strategy_d_daily_runner.py --summary   # aggregate from all runs

Does NOT modify production scripts; does NOT place real bets; does NOT call
NBA API (uses the local prediction cache).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# UTF-8 stdout (Wemby, Dončić, etc.)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

STRATEGY_D_STATS = {"blk", "fg3m", "stl"}
EDGE_THRESHOLD = 0.5
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
BETS_DIR = os.path.join(PROJECT_DIR, "data", "bets")
HIST_LINES_DIR = os.path.join(CACHE_DIR, "historical_lines")
DEFAULT_PROBE = os.path.join(CACHE_DIR, "probe_R15_tonight_slate_bets.json")

LEDGER_COLS = [
    "date", "game_id", "player", "stat", "line", "model_pred", "edge",
    "side", "odds", "stake", "status",
]


# --------------------------------------------------------------------------- #
# Prediction cache loader                                                     #
# --------------------------------------------------------------------------- #
def load_predictions(date_str: str) -> Dict[Tuple[str, str], Dict]:
    """Return {(player_lower, stat): {q10, q50, q90, sigma, team}} for the date.

    Empty dict if the parquet is missing. Forces stat keys to lowercase.
    """
    import pandas as pd
    path = os.path.join(CACHE_DIR, f"predictions_cache_{date_str}.parquet")
    if not os.path.exists(path):
        return {}
    df = pd.read_parquet(path)
    out: Dict[Tuple[str, str], Dict] = {}
    for _, r in df.iterrows():
        key = (str(r["player_name"]).strip().lower(), str(r["stat"]).lower())
        out[key] = {
            "q10": float(r["q10"]),
            "q50": float(r["q50"]),
            "q90": float(r["q90"]),
            "sigma": float(r["sigma"]),
            "team": str(r.get("team", "")),
            "player_id": int(r["player_id"]),
        }
    return out


# --------------------------------------------------------------------------- #
# Line source loader                                                          #
# --------------------------------------------------------------------------- #
def _scan_historical_lines(date_str: str) -> Optional[str]:
    """Look for any historical_lines file matching the date. None if absent."""
    if not os.path.isdir(HIST_LINES_DIR):
        return None
    cands = sorted(glob.glob(os.path.join(HIST_LINES_DIR, f"*{date_str}*")))
    return cands[0] if cands else None


def load_lines(date_str: str, game_id: Optional[str]) -> Tuple[List[Dict], str]:
    """Load (player, stat, side, line, odds, book, team) rows + a source label.

    Priority:
        1. probe_R15_tonight_slate_bets.json (the iter-7 dry-run source).
        2. data/cache/historical_lines/*<date>* (graceful fallback).
        3. Empty list (graceful degradation — no real lines available).
    """
    lines_src = "none"
    rows: List[Dict] = []

    if os.path.exists(DEFAULT_PROBE):
        try:
            d = json.load(open(DEFAULT_PROBE, encoding="utf-8"))
            for r in d.get("all_positive_bets_unfiltered", []) or []:
                rows.append({
                    "player": r["player"],
                    "team": r.get("team", ""),
                    "stat": str(r["stat"]).lower(),
                    "side": str(r["side"]).upper(),
                    "line": float(r["line"]),
                    "odds": int(r["odds"]),
                    "book": str(r.get("book", "")),
                    "game": d.get("game", ""),
                })
            lines_src = f"probe_R15 ({d.get('game', 'n/a')})"
            return rows, lines_src
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  [warn] could not parse {DEFAULT_PROBE}: {e}")

    hist = _scan_historical_lines(date_str)
    if hist:
        try:
            d = json.load(open(hist, encoding="utf-8"))
            for r in d if isinstance(d, list) else d.get("lines", []):
                rows.append({
                    "player": r.get("player", ""),
                    "team": r.get("team", ""),
                    "stat": str(r.get("stat", "")).lower(),
                    "side": str(r.get("side", "OVER")).upper(),
                    "line": float(r.get("line", 0.0)),
                    "odds": int(r.get("odds", -110)),
                    "book": r.get("book", ""),
                    "game": r.get("game", ""),
                })
            lines_src = f"historical_lines:{os.path.basename(hist)}"
            return rows, lines_src
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  [warn] could not parse {hist}: {e}")

    return rows, lines_src


# --------------------------------------------------------------------------- #
# Edge computation + filtering                                                #
# --------------------------------------------------------------------------- #
def build_recommendations(
    preds: Dict[Tuple[str, str], Dict],
    lines: List[Dict],
    stake: float,
) -> List[Dict]:
    """Filter to Strategy D stats; compute edge; dedupe to best odds per row.

    Returns a list sorted by |edge| descending.
    """
    # Aggregate to one row per (player, stat, line) — keep the best odds
    # for the model-implied side (so the OOS strategy maps to the best
    # available book price, not the first one encountered).
    agg: Dict[Tuple[str, str, float], Dict] = {}
    for r in lines:
        if r["stat"] not in STRATEGY_D_STATS:
            continue
        key = (r["player"].strip().lower(), r["stat"])
        p = preds.get(key)
        if p is None:
            continue
        model_pred = p["q50"]
        edge = model_pred - r["line"]
        if abs(edge) < EDGE_THRESHOLD:
            continue
        side = "OVER" if edge > 0 else "UNDER"
        # Only keep the book's row that matches our model-implied side
        if r["side"] != side:
            continue
        rec = {
            "player": r["player"],
            "team": r["team"] or p.get("team", ""),
            "stat": r["stat"],
            "line": r["line"],
            "model_pred": round(model_pred, 2),
            "edge": round(edge, 2),
            "side": side,
            "odds": int(r["odds"]),
            "book": r["book"],
            "stake": float(stake),
            "game": r.get("game", ""),
        }
        k2 = (rec["player"].lower(), rec["stat"], rec["line"])
        prior = agg.get(k2)
        # Prefer the most favourable odds for the bettor (higher payout):
        # for positive odds, larger; for negative odds, closer to zero.
        if prior is None or _payout_rank(rec["odds"]) > _payout_rank(prior["odds"]):
            agg[k2] = rec

    recs = list(agg.values())
    recs.sort(key=lambda r: abs(r["edge"]), reverse=True)
    return recs


def _payout_rank(odds: int) -> float:
    """Convert American odds to net payout per $1 — higher is better for bettor."""
    return (odds / 100.0) if odds > 0 else (100.0 / -odds)


# --------------------------------------------------------------------------- #
# Ledger I/O                                                                  #
# --------------------------------------------------------------------------- #
def ledger_path_for(date_str: str) -> str:
    return os.path.join(BETS_DIR, f"strategy_d_{date_str}.csv")


def append_ledger(date_str: str, game_id: str, recs: List[Dict]) -> int:
    if not recs:
        return 0
    os.makedirs(BETS_DIR, exist_ok=True)
    path = ledger_path_for(date_str)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(LEDGER_COLS)
        for r in recs:
            w.writerow([
                date_str, game_id or r.get("game", ""),
                r["player"], r["stat"], r["line"],
                r["model_pred"], r["edge"], r["side"],
                r["odds"], r["stake"], "dry-run-pending",
            ])
    return len(recs)


# --------------------------------------------------------------------------- #
# Summary printers                                                            #
# --------------------------------------------------------------------------- #
def _bucket_label(stat: str) -> str:
    return {"blk": "BLK", "fg3m": "FG3M", "stl": "STL"}[stat]


def print_slate_summary(date_str: str, game_label: str, recs: List[Dict],
                        total_exposure: float, n_no_pred: int) -> None:
    """Group recs by stat and print the iter-style summary table."""
    by_stat: Dict[str, List[Dict]] = {"blk": [], "fg3m": [], "stl": []}
    for r in recs:
        by_stat[r["stat"]].append(r)
    header = f"Strategy D — {date_str} {game_label}"
    print(f"\n  {header}")
    print("  " + "=" * len(header))
    if not recs:
        print("  (no Strategy D bets passed |edge| > 0.5 filter)")
        if n_no_pred:
            print(f"  [info] {n_no_pred} line(s) had no matching prediction in cache")
        return
    for stat in ("blk", "fg3m", "stl"):
        rows = by_stat[stat]
        if not rows:
            print(f"  {_bucket_label(stat)+' bets:':<11} 0")
            continue
        top = rows[0]
        odds_s = f"{top['odds']:+d}"
        descriptor = (f"{top['player']} {_bucket_label(stat)} "
                      f"{top['side'][0]} {top['line']:g} {odds_s}, "
                      f"edge {top['edge']:+.2f}")
        print(f"  {_bucket_label(stat)+' bets:':<11} {len(rows):>2} (top: {descriptor})")
    print(f"  {'-' * 6}")
    print(f"  Total exposure: ${total_exposure:,.0f} "
          f"({len(recs)} bets x ${recs[0]['stake']:.0f})")
    if n_no_pred:
        print(f"  [info] {n_no_pred} line(s) had no matching prediction in cache")


def print_ledger_sample(date_str: str, n: int = 5) -> None:
    path = ledger_path_for(date_str)
    if not os.path.exists(path):
        return
    print(f"\n  Ledger sample (first {n} rows) — {path}")
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i > n:
                break
            print("    " + line.rstrip())


def print_aggregate_summary() -> None:
    """Aggregate every data/bets/strategy_d_*.csv into a running ROI summary."""
    paths = sorted(glob.glob(os.path.join(BETS_DIR, "strategy_d_*.csv")))
    if not paths:
        print("  [summary] no strategy_d_*.csv ledgers found in data/bets/")
        return
    total_bets = 0
    total_staked = 0.0
    total_pnl = 0.0
    settled = 0
    by_stat: Dict[str, Dict[str, float]] = {
        s: {"bets": 0, "staked": 0.0, "pnl": 0.0} for s in ("blk", "fg3m", "stl")
    }
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                total_bets += 1
                try:
                    stake = float(row.get("stake") or 0)
                except ValueError:
                    stake = 0.0
                total_staked += stake
                stat = (row.get("stat") or "").lower()
                if stat in by_stat:
                    by_stat[stat]["bets"] += 1
                    by_stat[stat]["staked"] += stake
                status = (row.get("status") or "").lower()
                if status in ("win", "won"):
                    try:
                        odds = int(row.get("odds") or -110)
                    except ValueError:
                        odds = -110
                    profit = stake * _payout_rank(odds)
                    total_pnl += profit
                    if stat in by_stat:
                        by_stat[stat]["pnl"] += profit
                    settled += 1
                elif status in ("loss", "lost"):
                    total_pnl -= stake
                    if stat in by_stat:
                        by_stat[stat]["pnl"] -= stake
                    settled += 1
    roi = (total_pnl / total_staked * 100.0) if total_staked else 0.0
    print("\n  Strategy D — aggregate ledger summary")
    print("  =====================================")
    print(f"  Ledgers scanned : {len(paths)}")
    print(f"  Total bets      : {total_bets}")
    print(f"  Total staked    : ${total_staked:,.2f}")
    print(f"  Settled bets    : {settled} ({total_bets - settled} still dry-run-pending)")
    print(f"  Total PnL       : ${total_pnl:+,.2f}")
    print(f"  Running ROI     : {roi:+.2f}%")
    print("  ---- by stat ----")
    for s, agg in by_stat.items():
        s_roi = (agg["pnl"] / agg["staked"] * 100.0) if agg["staked"] else 0.0
        print(f"  {_bucket_label(s):<5} {agg['bets']:>3} bets  "
              f"staked ${agg['staked']:>9,.2f}  "
              f"pnl ${agg['pnl']:>+10,.2f}  ROI {s_roi:>+7.2f}%")


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Strategy D (BLK+FG3M+STL flat $100) daily betting runner",
    )
    ap.add_argument("--game-id", default=None,
                    help="Filter to a single game_id (informational; written to ledger).")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD (default: today)")
    ap.add_argument("--bankroll", type=float, default=10000.0,
                    help="Bankroll for stake sizing (default $10,000)")
    ap.add_argument("--stake-pct", type=float, default=1.0,
                    help="Per-bet stake as %% of bankroll (default 1.0%% = $100 on $10k)")
    ap.add_argument("--dry-run", default=True, action=argparse.BooleanOptionalAction,
                    help="Dry-run mode — write to ledger but DO NOT call sportsbook API. "
                         "True by default; the only mode tested.")
    ap.add_argument("--summary", action="store_true",
                    help="Print aggregate Strategy D stats across all prior ledgers and exit.")
    args = ap.parse_args(argv)

    if args.summary:
        print_aggregate_summary()
        return 0

    date_str = args.date or _date.today().isoformat()
    stake = round(args.bankroll * (args.stake_pct / 100.0), 2)

    print(f"\n  Strategy D daily runner — bankroll=${args.bankroll:,.0f}  "
          f"stake_pct={args.stake_pct:.2f}%  stake=${stake:.2f}/bet  "
          f"dry_run={args.dry_run}")

    preds = load_predictions(date_str)
    if not preds:
        print(f"  [fail] no predictions_cache_{date_str}.parquet — cannot proceed")
        return 1
    print(f"  [predictions] {len(preds)} (player, stat) entries loaded from cache")

    lines, lines_src = load_lines(date_str, args.game_id)
    print(f"  [lines] source={lines_src}  rows={len(lines)}")
    if not lines:
        print("  [warn] no line source available — nothing to compare against; exiting")
        return 0

    # Track how many lines lacked a matching prediction (informational only).
    n_no_pred = sum(
        1 for r in lines
        if r["stat"] in STRATEGY_D_STATS
        and (r["player"].strip().lower(), r["stat"]) not in preds
    )

    recs = build_recommendations(preds, lines, stake=stake)
    total_exposure = sum(r["stake"] for r in recs)

    # Determine game label for the header line.
    game_label = ""
    if lines and lines[0].get("game"):
        game_label = lines[0]["game"]
    elif args.game_id:
        game_label = args.game_id

    print_slate_summary(date_str, game_label, recs, total_exposure, n_no_pred)

    if args.dry_run:
        n = append_ledger(date_str, args.game_id or "", recs)
        print(f"\n  [dry-run] logged {n} recommendation(s) -> {ledger_path_for(date_str)}")
    else:
        print("\n  [warn] non-dry-run mode requested but no sportsbook API is wired.")
        print("         Doing nothing. Use scripts/place_bet.py for manual placement.")

    print_ledger_sample(date_str, n=5)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
