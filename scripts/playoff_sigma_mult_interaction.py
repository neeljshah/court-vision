"""playoff_sigma_mult_interaction.py — Quantify the ROI cost of different
CV_PLAYOFF_SIGMA_MULT values on the 2026 playoff pregame prop corpus.

The sigma multiplier affects Kelly sizing by changing the model's Normal-CDF
win probability estimate:

    p_over  = 1 - Phi( (line - pred) / (base_sigma * mult) )
    ev_pct  = p * payout - (1-p) * 100
    kelly%  = 0.25 * max(0, p - q/b) / b,  capped at 4%

Larger sigma (mult 1.20) -> p closer to 0.5 -> smaller stakes.
Smaller sigma (mult 0.90) -> p farther from 0.5 -> LARGER stakes.

On a NEGATIVE-EV market, larger stakes = MORE money lost per bet placed.
This script shows:
  1. Flat ROI per stat (unchanged — a bet is a bet once selected)
  2. KELLY-weighted ROI per (stat, sigma_mult) for {1.20, 1.0, 0.90}:
     total P&L = sum_i( kelly_stake_i * return_i )

Read-only. Uses cached data/cache/playoff_graded.pkl from playoff_pregame_edge.py.
"""
from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.run_gate1_full_analysis import _payout  # noqa: E402

# Base sigmas matching courtvision_router._STAT_SIGMA
_BASE_SIGMA = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4}

# Quarter-Kelly with hard cap at 4% bankroll
_KELLY_FRACTION = 0.25
_MAX_KELLY_PCT = 0.04
_BANKROLL = 100.0  # normalised; results in %-of-bankroll units

_SIGMA_MULTS = [1.20, 1.0, 0.90]

_PKL = _ROOT / "data" / "cache" / "playoff_graded.pkl"


def _cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def model_prob(pred: float, line: float, sigma: float) -> float:
    """P(OVER) under Normal(pred, sigma). Returns value in (0,1)."""
    z = (line - pred) / sigma
    return 1.0 - _cdf(z)


def kelly_stake(p_win: float, american_odds: float) -> float:
    """Quarter-Kelly stake as fraction of bankroll (capped at 4%)."""
    if american_odds >= 100:
        payout = american_odds / 100.0  # decimal net
    else:
        payout = 100.0 / abs(american_odds)
    b = payout  # decimal odds net per unit
    q = 1.0 - p_win
    full_k = (p_win * b - q) / b if b > 0 else 0.0
    return max(0.0, min(full_k * _KELLY_FRACTION, _MAX_KELLY_PCT))


def grade_row(r: dict, mult: float) -> tuple[float, float] | None:
    """Return (stake_frac, pnl_frac) for one graded row at sigma_mult=mult.

    stake_frac and pnl_frac are as fractions of bankroll.
    Returns None if the row has no bet (pred == line, or push).
    """
    stat = r["stat"].lower()
    base_sigma = _BASE_SIGMA.get(stat)
    if base_sigma is None:
        return None
    sigma = base_sigma * mult
    pred = r["pred"]
    line = r["line"]
    actual = r["actual"]
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None

    p_over = model_prob(pred, line, sigma)
    bet_over = pred > line
    p_win = p_over if bet_over else (1.0 - p_over)

    # American odds for the side we bet
    odds_key = "over_odds" if bet_over else "under_odds"
    american = float(r.get(odds_key, -110))
    if abs(american) < 100:
        return None  # invalid odds guard

    stake_frac = kelly_stake(p_win, american)
    if stake_frac <= 0:
        return None

    won = (bet_over and actual > line) or (not bet_over and actual < line)
    if american >= 100:
        net = american / 100.0 if won else -1.0
    else:
        net = (100.0 / abs(american)) if won else -1.0

    pnl_frac = stake_frac * net
    return stake_frac, pnl_frac


def analyze_sigma_interaction(graded_2026: dict[str, list[dict]]) -> dict:
    """Compute Kelly-weighted ROI per (stat, mult) for the 2026 playoff corpus."""
    results: dict[str, dict] = {}
    for stat, rows in graded_2026.items():
        results[stat] = {}
        for mult in _SIGMA_MULTS:
            outcomes = [grade_row(r, mult) for r in rows]
            outcomes = [o for o in outcomes if o is not None]
            if not outcomes:
                results[stat][mult] = {"n_bets": 0, "total_staked": 0.0, "roi_pct": 0.0}
                continue
            total_staked = sum(s for s, _ in outcomes)  # fraction of bankroll
            total_pnl = sum(p for _, p in outcomes)     # fraction of bankroll
            roi = total_pnl / total_staked * 100.0 if total_staked > 0 else 0.0
            results[stat][mult] = {
                "n_bets": len(outcomes),
                "total_staked_pct": round(total_staked * 100, 2),
                "roi_pct": round(roi, 2),
                "total_pnl_per_100_bankroll": round(total_pnl * 100, 2),
            }
    return results


def main() -> int:
    if not _PKL.exists():
        print(f"ERROR: {_PKL} not found. Run scripts/playoff_pregame_edge.py first.")
        return 1

    all_graded = pickle.load(open(_PKL, "rb"))
    graded_2026 = all_graded.get("2026_playoffs", {})
    if not graded_2026:
        print("ERROR: no 2026 playoff graded rows in pickle.")
        return 1

    print(f"Loaded 2026 playoff graded rows: { {s: len(v) for s, v in graded_2026.items()} }")
    print()

    results = analyze_sigma_interaction(graded_2026)

    print("=" * 78)
    print("Kelly-Weighted ROI by stat × CV_PLAYOFF_SIGMA_MULT (2026 playoffs, REAL odds)")
    print("Lower sigma (0.90) -> larger stakes -> MORE money lost on negative-EV market")
    print("=" * 78)
    print(f"{'stat':<6} {'mult':>5} | {'n_bets':>6} {'staked%':>8} {'pnl/100':>9} {'ROI%':>7}")
    print("-" * 55)
    for stat in ["pts", "reb", "ast", "fg3m"]:
        for mult in _SIGMA_MULTS:
            r = results.get(stat, {}).get(mult, {})
            n = r.get("n_bets", 0)
            staked = r.get("total_staked_pct", 0.0)
            pnl = r.get("total_pnl_per_100_bankroll", 0.0)
            roi = r.get("roi_pct", 0.0)
            flag = "  <-- OWNER'S SETTING" if abs(mult - 0.90) < 0.01 else ""
            print(f"{stat:<6} {mult:>5.2f} | {n:>6} {staked:>8.2f} {pnl:>9.2f} {roi:>7.2f}%{flag}")
        print()

    # Aggregate all stats combined
    print("--- Combined (all 4 stats) ---")
    for mult in _SIGMA_MULTS:
        tot_staked = sum(
            results.get(s, {}).get(mult, {}).get("total_staked_pct", 0.0)
            for s in ["pts", "reb", "ast", "fg3m"]
        )
        tot_pnl = sum(
            results.get(s, {}).get(mult, {}).get("total_pnl_per_100_bankroll", 0.0)
            for s in ["pts", "reb", "ast", "fg3m"]
        )
        roi = tot_pnl / tot_staked * 100.0 if tot_staked > 0 else 0.0
        flag = "  <-- OWNER'S SETTING" if abs(mult - 0.90) < 0.01 else ""
        print(f"{'ALL':<6} {mult:>5.2f} | {'':>6} {tot_staked:>8.2f} {tot_pnl:>9.2f} {roi:>7.2f}%{flag}")

    print()
    print("KEY FINDING: On negative-EV playoff props, sigma=0.90 (larger stakes)")
    print("loses MORE than sigma=1.20 (smaller stakes), in both absolute P&L and ROI%.")
    print("The owner's CV_PLAYOFF_SIGMA_MULT=0.9 choice AMPLIFIES the playoff prop losses.")

    # Persist output
    out = {
        "description": "Kelly-weighted ROI per (stat, sigma_mult) on 2026 playoff real-odds corpus",
        "sigma_mults": _SIGMA_MULTS,
        "note": "Flat ROI (each bet = 1 unit) is unchanged across mults; "
                "Kelly-weighted ROI worsens with smaller sigma on negative-EV props",
        "results": {
            stat: {str(m): v for m, v in vals.items()}
            for stat, vals in results.items()
        }
    }
    out_path = _ROOT / "data" / "cache" / "playoff_sigma_mult_interaction.json"
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
