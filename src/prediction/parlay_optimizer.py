"""
parlay_optimizer.py -- Phase E3: Correlation-adjusted parlay builder.

Standard parlays multiply odds assuming independence. This optimizer:
  1. Loads prop correlation matrix (built in Phase 4.6)
  2. Selects legs with lowest cross-correlations (independent outcomes)
  3. Penalizes same-game stacking of correlated stats (pts+ast same player)
  4. Returns optimal 2-4 leg parlays by expected value

Public API
----------
    build_parlay(candidates, n_legs, max_correlation)  -> dict
    get_optimal_parlays(season, n_results)             -> list[dict]
"""
from __future__ import annotations

import json
import math
import os
import sys
from itertools import combinations
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_CORR_PATH = os.path.join(PROJECT_DIR, "data", "nba", "prop_correlations.json")

# Minimum edge% required per leg to include in parlay
_MIN_LEG_EDGE = 0.03

# Max correlation between any two legs (Pearson)
_MAX_CORRELATION = 0.30


def _load_correlations() -> dict:
    """Load prop correlation matrix. Returns {(player1,stat1,player2,stat2): corr}."""
    if not os.path.exists(_CORR_PATH):
        return {}
    try:
        raw = json.load(open(_CORR_PATH))
        # Flatten to lookup dict
        lookup = {}
        for entry in raw.get("player_correlations", []):
            key = (entry["player1"], entry["stat1"], entry["player2"], entry["stat2"])
            lookup[key] = float(entry.get("corr", 0))
            key_rev = (entry["player2"], entry["stat2"], entry["player1"], entry["stat1"])
            lookup[key_rev] = float(entry.get("corr", 0))
        return lookup
    except Exception:
        return {}


def _get_correlation(corr_lookup: dict, leg1: dict, leg2: dict) -> float:
    """Look up correlation between two prop legs."""
    key = (leg1["player"], leg1["stat"], leg2["player"], leg2["stat"])
    return abs(corr_lookup.get(key, 0.0))


def _american_to_decimal(american: float) -> float:
    """Convert American odds to decimal."""
    if american >= 100:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def _ev(win_prob: float, decimal_odds: float) -> float:
    """Expected value of a bet."""
    return win_prob * decimal_odds - 1.0


def build_parlay(
    candidates:      list,
    n_legs:          int = 3,
    max_correlation: float = _MAX_CORRELATION,
) -> dict:
    """
    Build an optimal N-leg parlay from candidate prop bets.

    Args:
        candidates: list of {
            "player": str,
            "stat":   str,
            "side":   "over" | "under",
            "line":   float,
            "odds":   float,     # American odds
            "win_prob": float,   # our estimated win probability
        }
        n_legs:          Number of legs in the parlay
        max_correlation: Max allowed pairwise correlation

    Returns:
        {
            "legs":            list,   # selected legs
            "parlay_odds":     float,  # combined decimal odds
            "win_prob":        float,  # combined (independent assumption adjusted for corr)
            "ev":              float,  # expected value
            "correlation_penalty": float,
        }
    """
    corr_lookup = _load_correlations()

    # Filter to candidates with edge
    eligible = [c for c in candidates if c.get("win_prob", 0.5) - 0.5 >= _MIN_LEG_EDGE]

    best_combo = None
    best_ev = -999.0

    for combo in combinations(eligible, min(n_legs, len(eligible))):
        # Check max pairwise correlation
        max_corr = 0.0
        for i, j in combinations(range(len(combo)), 2):
            c = _get_correlation(corr_lookup, combo[i], combo[j])
            if c > max_corr:
                max_corr = c

        if max_corr > max_correlation:
            continue

        # Compute parlay metrics
        decimal_odds_list = [_american_to_decimal(leg.get("odds", -110)) for leg in combo]
        parlay_decimal = math.prod(decimal_odds_list)

        # Win prob: product adjusted for correlations
        base_prob = math.prod(leg.get("win_prob", 0.5) for leg in combo)
        corr_penalty = max_corr * 0.05 * (n_legs - 1)
        adj_prob = max(0.0, base_prob - corr_penalty)

        ev = _ev(adj_prob, parlay_decimal)

        if ev > best_ev:
            best_ev = ev
            best_combo = {
                "legs":                list(combo),
                "parlay_odds":         round(parlay_decimal, 2),
                "win_prob":            round(adj_prob, 4),
                "ev":                  round(ev, 4),
                "max_pairwise_corr":   round(max_corr, 3),
                "correlation_penalty": round(corr_penalty, 4),
            }

    if best_combo is None:
        return {
            "legs": [], "parlay_odds": 0.0, "win_prob": 0.0, "ev": 0.0,
            "error": "No valid combination found",
        }
    return best_combo


def get_optimal_parlays(
    season:    str = "2024-25",
    n_results: int = 5,
    n_legs:    int = 3,
) -> list:
    """
    Return the top N optimal parlays for tonight based on current edges.

    Returns:
        list of parlay dicts, sorted by EV descending.
    """
    # Load today's edges
    edges_path = os.path.join(PROJECT_DIR, "data", "nba", f"todays_edges_{season}.json")
    if not os.path.exists(edges_path):
        return []

    try:
        candidates = json.load(open(edges_path))
    except Exception:
        return []

    # Build 2, 3, and 4-leg parlays
    results = []
    for legs in (2, 3, 4):
        p = build_parlay(candidates, n_legs=legs)
        if p.get("ev", 0) > 0:
            p["n_legs"] = legs
            results.append(p)

    results.sort(key=lambda x: -x.get("ev", 0))
    return results[:n_results]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--legs",   type=int, default=3)
    args = parser.parse_args()

    parlays = get_optimal_parlays(args.season, n_results=5, n_legs=args.legs)
    if not parlays:
        print("[parlay_optimizer] No parlays found. Run /edge/today first to generate candidates.")
    for i, p in enumerate(parlays, 1):
        print(f"\nParlay #{i} ({p.get('n_legs', args.legs)} legs):")
        print(f"  Odds: {p['parlay_odds']:.2f}x  WinProb: {p['win_prob']:.1%}  EV: {p['ev']:+.3f}")
        for leg in p.get("legs", []):
            print(f"    {leg.get('player'):20s}  {leg.get('stat')} {leg.get('side')} {leg.get('line')}")
