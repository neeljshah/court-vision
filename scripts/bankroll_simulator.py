"""
bankroll_simulator.py — Monte Carlo bankroll simulation for betting sequences.

Simulates N independent betting sequences drawn from an edge distribution,
computes drawdown and ruin probability.

Public API
----------
    simulate_bankroll(n_bets, edge_mean, edge_std, kelly_fraction,
                      bankroll, n_simulations, ruin_threshold, seed) -> dict
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np


def simulate_bankroll(
    n_bets: int = 500,
    edge_mean: float = 0.04,
    edge_std: float = 0.02,
    kelly_fraction: float = 0.25,
    bankroll: float = 1000.0,
    n_simulations: int = 1000,
    ruin_threshold: float = 0.20,
    odds: int = -110,
    seed: Optional[int] = None,
) -> Dict:
    """
    Monte Carlo bankroll simulation.

    For each simulation:
      1. Draw n_bets edges from N(edge_mean, edge_std).
      2. Compute kelly bet size for each edge.
      3. Resolve each bet: win with probability (implied_prob + edge).
      4. Track bankroll path, max drawdown, and ruin (bankroll < ruin_threshold * start).

    Args:
        n_bets:          Bets per simulation.
        edge_mean:       Mean edge fraction (e.g. 0.04 = 4%).
        edge_std:        Std dev of edge distribution.
        kelly_fraction:  Fractional Kelly multiplier (0.25 = quarter-Kelly).
        bankroll:        Starting bankroll in dollars.
        n_simulations:   Number of Monte Carlo paths.
        ruin_threshold:  Fraction of starting bankroll — below this counts as ruin.
        odds:            American odds for all bets (default -110).
        seed:            Optional RNG seed for reproducibility.

    Returns:
        {
            "ruin_prob":              float,  # P(bankroll drops below ruin_threshold)
            "max_drawdown_pct":       float,  # median max-drawdown across simulations
            "final_bankroll_median":  float,  # median ending bankroll
            "final_bankroll_p10":     float,  # 10th-percentile ending bankroll
            "final_bankroll_p90":     float,  # 90th-percentile ending bankroll
            "n_simulations":          int,
            "n_bets":                 int,
            "edge_mean":              float,
            "kelly_fraction":         float,
        }
    """
    rng = np.random.default_rng(seed)

    # Pre-compute payout from odds
    if odds >= 0:
        payout = odds / 100.0
    else:
        payout = 100.0 / abs(odds)
    implied_prob = 1.0 / (1.0 + payout)

    ruin_count = 0
    final_bankrolls: list = []
    max_drawdowns: list = []
    ruin_floor = bankroll * ruin_threshold

    for _ in range(n_simulations):
        bk = bankroll
        peak = bankroll
        ruined = False
        max_dd = 0.0

        edges = rng.normal(edge_mean, edge_std, n_bets)

        for edge in edges:
            if bk <= 0:
                ruined = True
                break

            # Kelly bet size
            win_prob = min(0.95, max(0.05, implied_prob + edge))
            q = 1.0 - win_prob
            full_k = (win_prob * payout - q) / payout if payout > 0 else 0.0
            f = max(0.0, full_k * kelly_fraction)
            f = min(f, 0.04)  # 4% cap

            bet_size = f * bk

            # Resolve bet
            won = rng.random() < win_prob
            bk += bet_size * payout if won else -bet_size

            if bk > peak:
                peak = bk
            dd = (peak - bk) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            if bk < ruin_floor:
                ruined = True
                break

        if ruined:
            ruin_count += 1
        final_bankrolls.append(max(0.0, bk))
        max_drawdowns.append(max_dd)

    fb = np.array(final_bankrolls)
    dd = np.array(max_drawdowns)

    return {
        "ruin_prob": round(ruin_count / n_simulations, 4),
        "max_drawdown_pct": round(float(np.median(dd)) * 100, 2),
        "final_bankroll_median": round(float(np.median(fb)), 2),
        "final_bankroll_p10": round(float(np.percentile(fb, 10)), 2),
        "final_bankroll_p90": round(float(np.percentile(fb, 90)), 2),
        "n_simulations": n_simulations,
        "n_bets": n_bets,
        "edge_mean": edge_mean,
        "kelly_fraction": kelly_fraction,
    }


if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Bankroll Monte Carlo simulator")
    parser.add_argument("--n-bets", type=int, default=500)
    parser.add_argument("--edge-mean", type=float, default=0.04)
    parser.add_argument("--edge-std", type=float, default=0.02)
    parser.add_argument("--kelly", type=float, default=0.25)
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--sims", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    result = simulate_bankroll(
        n_bets=args.n_bets, edge_mean=args.edge_mean, edge_std=args.edge_std,
        kelly_fraction=args.kelly, bankroll=args.bankroll,
        n_simulations=args.sims, seed=args.seed,
    )
    print(json.dumps(result, indent=2))
