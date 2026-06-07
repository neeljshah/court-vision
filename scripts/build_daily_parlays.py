"""build_daily_parlays.py — Daily 3-leg parlay slate CLI (Iter-43).

Reads today's single-leg bet log (produced by compare_to_lines --bet-log)
and outputs ranked 3-leg parlays with SGP-adjusted EV and Kelly stakes.

Usage
-----
    # Minimal: reads today's bet log from data/bets/<today>.csv
    python scripts/build_daily_parlays.py

    # Explicit input file + options
    python scripts/build_daily_parlays.py --bets data/bets/2026-05-27.csv \
        --top-n 10 --bankroll 1000 --min-ev-pct 20 --out-csv data/parlays/3leg_2026-05-27.csv

    # Dry-run against a custom CSV (same schema as bet log)
    python scripts/build_daily_parlays.py --bets tonight.csv --bankroll 500

Input CSV schema (compare_to_lines --bet-log output)
------------------------------------------------------
    timestamp, date, player, stat, line, side, model, edge,
    prob, odds, ev_per_dollar, kelly_pct, kelly_stake, bankroll

Output
------
    Console table of top parlays sorted by expected SGP-adjusted ROI.
    Optional --out-csv writes the full ranked DataFrame to CSV.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date as _date

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, SCRIPTS_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from lib_betting_validation import safe_odds  # Bug 10 guard

from src.prediction.parlay_constructor import (  # noqa: E402
    build_parlay_candidates,
    kelly_parlay_stake,
    rank_parlays,
)


def _default_bet_log() -> str:
    today = _date.today().isoformat()
    return os.path.join(PROJECT_DIR, "data", "bets", f"{today}.csv")


def _load_bets(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(f"[build_daily_parlays] ERROR: bet log not found: {path}")
        print("  Run: python scripts/compare_to_lines.py <lines.csv> --bet-log")
        sys.exit(1)

    df = pd.read_csv(path, encoding="utf-8")
    df.columns = [c.lower().strip() for c in df.columns]

    # Normalise column names: ev_per_dollar → ev, over_odds → odds
    if "ev_per_dollar" in df.columns and "ev" not in df.columns:
        df.rename(columns={"ev_per_dollar": "ev"}, inplace=True)
    if "over_odds" in df.columns and "odds" not in df.columns:
        df.rename(columns={"over_odds": "odds"}, inplace=True)
    if "odds" in df.columns:  # Bug 10 guard
        df["odds"] = df["odds"].apply(safe_odds)

    return df


def _print_slate(ranked: pd.DataFrame, bankroll: float, top_n: int) -> None:
    display = ranked.head(top_n)
    if display.empty:
        print("\n  (no parlays cleared the EV gate)")
        return

    print(f"\n  TOP {len(display)} 3-LEG PARLAYS  (SGP-adjusted EV, sorted by ROI%)")
    print("  " + "-" * 94)
    hdr = (f"  {'#':>3}  {'Players':<28}  {'Stats':<20}  "
           f"{'HitRate':>7}  {'Odds':>6}  {'ROI%':>7}  {'Kelly$':>7}")
    print(hdr)
    print("  " + "-" * 94)

    for _, row in display.iterrows():
        parlay_dict = {
            "hit_rate_adj": row["hit_rate_adj"],
            "decimal_odds": row["decimal_odds"],
            "sgp_payout_adj": row["sgp_payout_adj"],
        }
        stake = kelly_parlay_stake(parlay_dict, bankroll=bankroll, kelly_fraction=0.10)
        players = row["player_combo"][:28]
        stats = row["stat_combo"][:20]
        print(
            f"  {int(row['rank']):>3}  {players:<28}  {stats:<20}  "
            f"{row['hit_rate_adj']:>6.1%}  "
            f"{row['american_odds']:>+6d}  "
            f"{row['expected_roi_sgp_pct']:>+6.1f}%  "
            f"${stake:>6.2f}"
        )

    print()
    viable = (ranked["hit_rate_adj"] > 0.144).sum()
    print(f"  Total viable combos (hit > 14.4% break-even): {viable}")
    print(f"  Iter-42 baseline: 564 viable / +50.53% SGP-adj ROI")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rank 3-leg parlays from today's single-leg bet log (Iter-43)."
    )
    ap.add_argument("--bets", default=None,
                    help="Path to single-leg bet log CSV. "
                         "Default: data/bets/<today>.csv")
    ap.add_argument("--top-n", type=int, default=15,
                    help="Number of parlays to display (default 15)")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll for Kelly sizing (default $1000)")
    ap.add_argument("--min-ev-pct", type=float, default=0.0,
                    help="Minimum expected SGP ROI%% to include (default 0)")
    ap.add_argument("--out-csv", default=None,
                    help="Optional: write full ranked slate to this CSV path")
    ap.add_argument("--no-same-player", action="store_true",
                    help="Exclude same-player combos (stricter independence)")
    args = ap.parse_args()

    bet_path = args.bets or _default_bet_log()
    print(f"[build_daily_parlays] Loading bets from: {bet_path}")
    bets_df = _load_bets(bet_path)

    # Keep only OVER bets (constructor also enforces this, but report counts)
    over_bets = bets_df[bets_df.get("side", pd.Series(dtype=str)).str.upper() == "OVER"]
    total_bets = len(bets_df)
    over_count = len(over_bets)
    print(f"[build_daily_parlays] {total_bets} total bets, {over_count} OVER bets")

    if over_count < 3:
        print("[build_daily_parlays] Need ≥3 OVER bets to form a 3-leg parlay. Exiting.")
        return 1

    print("[build_daily_parlays] Enumerating 3-leg combos...")
    candidates = build_parlay_candidates(bets_df)
    print(f"[build_daily_parlays] {len(candidates)} total combos enumerated")

    if args.no_same_player and not candidates.empty:
        candidates = candidates[~candidates["is_same_player"]]
        print(f"[build_daily_parlays] {len(candidates)} after excluding same-player")

    if args.min_ev_pct > 0 and not candidates.empty:
        candidates = candidates[candidates["expected_roi_sgp_pct"] >= args.min_ev_pct]
        print(f"[build_daily_parlays] {len(candidates)} after min-ev-pct={args.min_ev_pct}%")

    ranked = rank_parlays(candidates)
    print(f"[build_daily_parlays] {len(ranked)} positive-ROI parlays ranked")

    _print_slate(ranked, bankroll=args.bankroll, top_n=args.top_n)

    if args.out_csv and not ranked.empty:
        # Resolve leg dicts to flat columns for CSV
        out = ranked.drop(columns=["leg_0", "leg_1", "leg_2"], errors="ignore")
        out["kelly_stake"] = out.apply(
            lambda r: kelly_parlay_stake(r.to_dict(), args.bankroll, 0.10),
            axis=1,
        )
        os.makedirs(os.path.dirname(args.out_csv) or ".", exist_ok=True)
        out.to_csv(args.out_csv, index=False)
        print(f"[build_daily_parlays] Written: {args.out_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
