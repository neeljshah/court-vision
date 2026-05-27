"""build_parlays.py — CLI for offline parlay generation.

Reuses api.courtvision_router._build_slate() to load + grade the night's
slate, then enumerates Monte-Carlo-priced parlays via parlay_engine.ParlayEngine.

Usage:
    python scripts/build_parlays.py --date 2026-05-27 --max-legs 5 \
        --min-ev-pct 5 --top-n 10 --bankroll 100 --seed 0
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.courtvision_router import _build_slate  # noqa: E402
from src.prediction.parlay_engine import ParlayEngine  # noqa: E402


_CSV_COLUMNS = [
    "parlay_id", "date", "n_legs", "leg_bet_ids", "leg_summary",
    "p_hit_model", "p_hit_market_naive",
    "combined_odds_american", "combined_odds_decimal",
    "ev_pct", "kelly_stake_dollars",
    "avg_pair_correlation", "same_game_legs", "narrative",
]


def _write_csv(out_path: Path, parlays: list[dict], date: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        w.writeheader()
        for p in parlays:
            w.writerow({
                "parlay_id": p["parlay_id"], "date": date, "n_legs": p["n_legs"],
                "leg_bet_ids": "|".join(p["legs"]),
                "leg_summary": p["narrative"].split(": ", 1)[-1].split(" — ", 1)[0],
                "p_hit_model": p["p_hit_model"],
                "p_hit_market_naive": p["p_hit_market_naive"],
                "combined_odds_american": p["combined_odds_american"],
                "combined_odds_decimal": p["combined_odds_decimal"],
                "ev_pct": p["ev_pct"],
                "kelly_stake_dollars": p["kelly_stake_dollars"],
                "avg_pair_correlation": p["avg_pair_correlation"],
                "same_game_legs": p["same_game_legs"],
                "narrative": p["narrative"],
            })


def _print_top_n(parlays: list[dict], n: int) -> None:
    if not parlays:
        print("(no parlays cleared the EV gate)")
        return
    print(f"\nTOP {min(n, len(parlays))} parlays (sorted by EV%)")
    print("-" * 84)
    for i, p in enumerate(parlays[:n], start=1):
        tag = "SGP" if p["same_game_legs"] >= 2 else "multi"
        odds = p["combined_odds_american"]
        odds_s = f"+{odds}" if odds >= 0 else f"{odds}"
        print(
            f"#{i:<2} {p['n_legs']}-leg {tag:5s} {odds_s:>6s}  "
            f"model {p['p_hit_model']*100:5.1f}%  "
            f"market {p['p_hit_market_naive']*100:5.1f}%  "
            f"EV {p['ev_pct']:+7.2f}%  K ${p['kelly_stake_dollars']:>5.2f}"
        )
        print(f"     {p['narrative'].split(': ', 1)[-1].split(' — ', 1)[0]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Monte-Carlo parlays for a date.")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--max-legs", type=int, default=5)
    ap.add_argument("--min-ev-pct", type=float, default=5.0)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--bankroll", type=float, default=100.0,
                    help="(reserved; engine uses $100 internally)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    envelope = _build_slate(args.date)
    bets = envelope.get("bets", [])
    if not bets:
        print(f"[build_parlays] no graded bets for {args.date}", file=sys.stderr)
        return 1
    if not envelope.get("has_lines"):
        print(f"[build_parlays] slate has no lines for {args.date} — "
              "EV cannot be computed. Drop "
              f"data/lines/lines_{args.date}.csv first.", file=sys.stderr)
        return 1

    engine = ParlayEngine(bets, rng_seed=args.seed)
    parlays = engine.enumerate_parlays(max_legs=args.max_legs,
                                       min_ev_pct=args.min_ev_pct)

    out_csv = ROOT / "data" / "parlays" / f"parlays_{args.date}.csv"
    _write_csv(out_csv, parlays, args.date)
    print(f"[build_parlays] {len(parlays)} parlays -> {out_csv}")
    _print_top_n(parlays, args.top_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
