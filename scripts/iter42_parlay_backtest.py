"""iter42_parlay_backtest.py — Parlay execution backtest on 2,688-bet 2025-26 eval.

GOAL: Validate the Iter-41 estimate of +57-85% ROI on 2-3 leg parlays by
running an actual PnL simulation on real outcome data from the 5,240-row
2025-26 eval CSV.

APPROACH:
  1. Load 5,240-row _iter35_merged_2025_26.csv (actual_value + closing_line + odds)
  2. For each player-game in the eval, stochastically sample which stats fire as
     production bets using Bayesian-corrected per-row selection probabilities.

     Bayesian selection: The production model achieves high hit rates by selecting
     positive-edge rows. We don't have per-row predictions, so we use Bayes' theorem
     to condition selection probability on the actual outcome (over_hit):
       P(bet | over_hit) = prod_hit_rate * selection_rate / raw_over_rate
       P(bet | under_hit) = (1-prod_hit_rate) * selection_rate / raw_under_rate
     This correctly reproduces the production hit rates while preserving real
     correlation structure between stats.

  3. For each player-game with 2+ fired bets:
     - Enumerate all 2-leg combos (EXCLUDING fg3m+pts pairs)
     - Enumerate all 3-leg combos (EXCLUDING any combo containing fg3m+pts pair)
     - Bet direction: OVER (model only takes positive-edge bets)
     - Parlay hit = ALL legs hit (actual > line, no pushes)
     - Per-leg decimal odds from CSV; compound to get parlay decimal
  4. Aggregate PnL, hit rates, ROI
  5. Report: raw compound odds + SGP-corrected (-15% penalty) + per-pair breakdown

EXCLUDED PAIRS: fg3m+pts (phi=0.513 — definitional correlation, 3PM directly
contributes to PTS. Not independent bets.)

Single-leg baseline: +22.04% ROI (iter-39 full production stack)
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "_iter35_merged_2025_26.csv",
)
VAULT_STRATEGY_DIR = os.path.join(PROJECT_DIR, "vault", "Strategy")
REPORT_PATH = os.path.join(VAULT_STRATEGY_DIR, "Parlay Backtest 2026-05-27.md")

# ── Production context (iter-39 shipped config) ────────────────────────────────
ALL_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]

# Iter-39 per-stat n_bets and ROI (flat -110)
ITER39_N_BETS: Dict[str, int] = {
    "pts": 527, "reb": 157, "ast": 374,
    "fg3m": 74, "stl": 634, "blk": 631,
}
ITER39_ROI_PCT: Dict[str, float] = {
    "pts": 16.05, "reb": 16.73, "ast": 24.04,
    "fg3m": 26.39, "stl": 15.02, "blk": 26.86,
}
ITER39_HIT_RATE: Dict[str, float] = {
    "pts": 0.5847, "reb": 0.5982, "ast": 0.6716,
    "fg3m": 0.7183, "stl": 0.6183, "blk": 0.6654,
}
ITER39_AGG_ROI: float = 22.04
ITER39_TOTAL_BETS: int = 2397

# ── Parlay constants ──────────────────────────────────────────────────────────
SGP_PENALTY = 0.15            # Real-world SGP correlation penalty on payout
DEFINITIONAL_PAIRS = {        # Forbidden parlay pairs (definitional correlation)
    frozenset(["fg3m", "pts"]),
}

# ── Eval CSV row counts per stat (for selection rate derivation) ───────────────
EVAL_ROW_COUNTS: Dict[str, int] = {
    "pts": 1113, "reb": 1070, "ast": 962,
    "fg3m": 945, "stl": 422, "blk": 728,
}

# ── Raw OVER hit rates from eval CSV (all rows, unfiltered) ───────────────────
# These reflect market calibration (~47-49% for pts/reb/ast, lower for blk)
RAW_OVER_RATES: Dict[str, float] = {
    "pts": 0.471, "reb": 0.473, "ast": 0.471,
    "fg3m": 0.450, "stl": 0.489, "blk": 0.384,
}

# ── Aggregate selection rates (iter-39 bets / eval rows, capped at 1.0) ───────
SELECTION_RATES: Dict[str, float] = {
    stat: min(1.0, ITER39_N_BETS[stat] / EVAL_ROW_COUNTS[stat])
    for stat in ALL_STATS
}

# ── Bayesian per-row selection probabilities ───────────────────────────────────
# P(prod_bet | over_hit=True) and P(prod_bet | over_hit=False)
# Derived from: prod_hit_rate = P(over|bet), selection_rate = P(bet), raw_rate = P(over)
# P(bet|over) = P(over|bet)*P(bet)/P(over) = prod_hit_rate*sel_rate/raw_over_rate
# P(bet|under) = P(under|bet)*P(bet)/P(under) = (1-prod_hit_rate)*sel_rate/(1-raw_over_rate)
def _compute_bayesian_sel(stat: str) -> Tuple[float, float]:
    """Return (p_bet_given_over, p_bet_given_under) for a stat."""
    ph = ITER39_HIT_RATE[stat]
    s = SELECTION_RATES[stat]
    ro = RAW_OVER_RATES[stat]
    p_over = min(1.0, ph * s / ro) if ro > 1e-9 else s
    p_under = min(1.0, (1.0 - ph) * s / (1.0 - ro)) if (1.0 - ro) > 1e-9 else s
    return p_over, p_under

BAYESIAN_SEL: Dict[str, Tuple[float, float]] = {
    stat: _compute_bayesian_sel(stat) for stat in ALL_STATS
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def us_to_decimal(odds_str: str) -> float:
    """Convert US odds string to decimal odds (returns on 1 unit stake including stake)."""
    try:
        o = int(odds_str.strip())
        if o == 0:
            return 1.909090909  # default -110
        if o > 0:
            return 1.0 + o / 100.0
        else:
            return 1.0 + 100.0 / abs(o)
    except (ValueError, TypeError):
        return 1.909090909  # default -110 decimal


def is_forbidden_pair(stat_a: str, stat_b: str) -> bool:
    """Return True if (stat_a, stat_b) is a definitionally-correlated pair."""
    return frozenset([stat_a, stat_b]) in DEFINITIONAL_PAIRS


def is_forbidden_combo(stats: Tuple[str, ...]) -> bool:
    """Return True if the combo contains any forbidden pair."""
    for a, b in combinations(stats, 2):
        if is_forbidden_pair(a, b):
            return True
    return False


# ── Data loading ──────────────────────────────────────────────────────────────

def load_eval_data() -> List[Dict]:
    """Load the 5,240-row merged eval CSV and compute bet outcomes."""
    rows = []
    with open(EVAL_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            stat = r.get("stat", "").lower()
            if stat not in ALL_STATS:
                continue
            try:
                actual = float(r["actual_value"])
                line = float(r["closing_line"])
                over_odds = us_to_decimal(r.get("over_odds", "-110"))
                under_odds = us_to_decimal(r.get("under_odds", "-110"))
            except (ValueError, TypeError, KeyError):
                continue
            push = abs(actual - line) < 1e-9
            over_hit = (actual > line) and not push
            rows.append({
                "player": r["player"],
                "date": r["date"],
                "stat": stat,
                "actual": actual,
                "line": line,
                "over_odds": over_odds,
                "under_odds": under_odds,
                "over_hit": over_hit,
                "push": push,
            })
    return rows


def build_player_game_map(rows: List[Dict]) -> Dict[Tuple, Dict[str, Dict]]:
    """Group rows by (player, date) -> {stat -> data}. Keep first row per stat."""
    pg: Dict[Tuple, Dict[str, Dict]] = defaultdict(dict)
    for r in rows:
        key = (r["player"], r["date"])
        stat = r["stat"]
        if stat not in pg[key]:
            pg[key][stat] = r
    return dict(pg)


# ── Production bet simulation ─────────────────────────────────────────────────

def sample_production_bets(
    pg_map: Dict[Tuple, Dict[str, Dict]],
    selection_rates: Dict[str, float],
    rng: np.random.Generator,
    n_trials: int = 500,
) -> Dict:
    """
    Stochastic simulation: for each player-game, sample which stats fire as
    production bets using BAYESIAN-CORRECTED per-row selection probabilities.

    Bayesian selection: P(bet | over_hit) and P(bet | under_hit) are computed
    from iter-39 production hit rates, aggregate selection rates, and raw OVER
    rates in the eval CSV. This faithfully reproduces per-stat production hit
    rates while preserving real inter-stat correlation structure.

    Run n_trials independent trials and average to reduce sampling noise.
    """
    # Collect all 2-leg and 3-leg bet events across trials
    pair_stats: Dict[Tuple[str, str], Dict] = defaultdict(
        lambda: {"n": 0, "hit": 0, "stake": 0.0, "pnl_raw": 0.0}
    )
    triple_stats: Dict[Tuple[str, str, str], Dict] = defaultdict(
        lambda: {"n": 0, "hit": 0, "stake": 0.0, "pnl_raw": 0.0}
    )
    total_2leg: Dict = {"n": 0, "hit": 0, "stake": 0.0, "pnl_raw": 0.0}
    total_3leg: Dict = {"n": 0, "hit": 0, "stake": 0.0, "pnl_raw": 0.0}

    pg_items = list(pg_map.items())
    # Standard -110 decimal for normalized comparison to single-leg baseline
    DECIMAL_M110 = 1.0 + 100.0 / 110.0

    for trial in range(n_trials):
        for key, stat_map in pg_items:
            # Bayesian-corrected sampling: condition on actual over_hit
            fired = []
            for stat, r in stat_map.items():
                if r["push"]:
                    continue
                p_over_sel, p_under_sel = BAYESIAN_SEL.get(stat, (0.5, 0.5))
                # Use over_hit to pick the Bayesian-conditioned probability
                sel_prob = p_over_sel if r["over_hit"] else p_under_sel
                if rng.random() < sel_prob:
                    fired.append(stat)
            if len(fired) < 2:
                continue

            # ── 2-leg combos ─────────────────────────────────────────────────
            for stat_a, stat_b in combinations(fired, 2):
                if is_forbidden_pair(stat_a, stat_b):
                    continue
                da = stat_map[stat_a]
                db = stat_map[stat_b]
                if da["push"] or db["push"]:
                    continue
                # Raw: actual market odds from CSV
                dec_a = da["over_odds"]
                dec_b = db["over_odds"]
                compound_raw = dec_a * dec_b
                # Normalized: -110/-110 standard odds (for baseline comparison)
                compound_norm = DECIMAL_M110 * DECIMAL_M110
                hit = da["over_hit"] and db["over_hit"]
                pnl_raw = (compound_raw - 1.0) if hit else -1.0
                pnl_norm = (compound_norm - 1.0) if hit else -1.0
                pair_key = tuple(sorted([stat_a, stat_b]))
                pair_stats[pair_key]["n"] += 1
                pair_stats[pair_key]["hit"] += int(hit)
                pair_stats[pair_key]["stake"] += 1.0
                pair_stats[pair_key]["pnl_raw"] += pnl_raw
                pair_stats[pair_key].setdefault("pnl_norm", 0.0)
                pair_stats[pair_key]["pnl_norm"] += pnl_norm
                total_2leg["n"] += 1
                total_2leg["hit"] += int(hit)
                total_2leg["stake"] += 1.0
                total_2leg["pnl_raw"] += pnl_raw
                total_2leg.setdefault("pnl_norm", 0.0)
                total_2leg["pnl_norm"] += pnl_norm

            # ── 3-leg combos ─────────────────────────────────────────────────
            if len(fired) >= 3:
                for combo in combinations(fired, 3):
                    if is_forbidden_combo(combo):
                        continue
                    if any(stat_map[s]["push"] for s in combo):
                        continue
                    dec_product = 1.0
                    all_hit = True
                    for s in combo:
                        dec_product *= stat_map[s]["over_odds"]
                        if not stat_map[s]["over_hit"]:
                            all_hit = False
                    compound_norm3 = DECIMAL_M110 ** 3
                    pnl_raw = (dec_product - 1.0) if all_hit else -1.0
                    pnl_norm = (compound_norm3 - 1.0) if all_hit else -1.0
                    triple_key = tuple(sorted(combo))
                    triple_stats[triple_key]["n"] += 1
                    triple_stats[triple_key]["hit"] += int(all_hit)
                    triple_stats[triple_key]["stake"] += 1.0
                    triple_stats[triple_key]["pnl_raw"] += pnl_raw
                    triple_stats[triple_key].setdefault("pnl_norm", 0.0)
                    triple_stats[triple_key]["pnl_norm"] += pnl_norm
                    total_3leg["n"] += 1
                    total_3leg["hit"] += int(all_hit)
                    total_3leg["stake"] += 1.0
                    total_3leg["pnl_raw"] += pnl_raw
                    total_3leg.setdefault("pnl_norm", 0.0)
                    total_3leg["pnl_norm"] += pnl_norm

    # Average across trials (all counts are per-trial sums)
    def avg_dict(d: Dict, trials: int) -> Dict:
        result = {
            "n": d["n"] / trials,
            "hit": d["hit"] / trials,
            "stake": d["stake"] / trials,
            "pnl_raw": d["pnl_raw"] / trials,
        }
        # Preserve pnl_norm if it was accumulated
        if "pnl_norm" in d:
            result["pnl_norm"] = d["pnl_norm"] / trials
        return result

    # Normalize pair/triple dicts and compute ROI
    def compute_roi(agg: Dict) -> Dict:
        n = agg["n"]
        if n < 1:
            return {**agg, "hit_rate": 0.0, "roi_raw": 0.0, "roi_norm": 0.0, "roi_sgp": 0.0, "roi_norm_sgp": 0.0}
        hit_rate = agg["hit"] / n
        roi_raw = (agg["pnl_raw"] / agg["stake"]) * 100.0
        # Normalized ROI (standardized -110/-110 odds for direct baseline comparison)
        pnl_norm = agg.get("pnl_norm", agg["pnl_raw"])
        roi_norm = (pnl_norm / agg["stake"]) * 100.0
        # SGP correction: sportsbook reduces payout by 15% on parlay wins
        hits = agg["hit"]
        losses = agg["stake"] - hits
        # Apply SGP penalty to RAW (actual odds) wins
        if hits > 0:
            avg_net_win_raw = (agg["pnl_raw"] + losses) / hits
            pnl_sgp = hits * avg_net_win_raw * (1.0 - SGP_PENALTY) - losses
            avg_net_win_norm = (pnl_norm + losses) / hits
            pnl_norm_sgp = hits * avg_net_win_norm * (1.0 - SGP_PENALTY) - losses
        else:
            pnl_sgp = agg["pnl_raw"]
            pnl_norm_sgp = pnl_norm
        roi_sgp = (pnl_sgp / agg["stake"]) * 100.0
        roi_norm_sgp = (pnl_norm_sgp / agg["stake"]) * 100.0
        return {
            **agg, "hit_rate": hit_rate,
            "roi_raw": roi_raw, "roi_norm": roi_norm,
            "roi_sgp": roi_sgp, "roi_norm_sgp": roi_norm_sgp,
        }

    pair_results = {}
    for k, v in pair_stats.items():
        av = avg_dict(v, n_trials)
        pair_results[k] = compute_roi(av)

    triple_results = {}
    for k, v in triple_stats.items():
        av = avg_dict(v, n_trials)
        triple_results[k] = compute_roi(av)

    t2 = avg_dict(total_2leg, n_trials)
    t3 = avg_dict(total_3leg, n_trials)

    return {
        "pair_results": pair_results,
        "triple_results": triple_results,
        "total_2leg": compute_roi(t2),
        "total_3leg": compute_roi(t3),
        "n_trials": n_trials,
    }


# ── Report generation ─────────────────────────────────────────────────────────

def format_report(
    results: Dict,
    marginal_hit_rates: Dict[str, float],
) -> str:
    t2 = results["total_2leg"]
    t3 = results["total_3leg"]
    pair_results = results["pair_results"]
    triple_results = results["triple_results"]
    n_trials = results["n_trials"]

    # Sort pairs by raw ROI
    sorted_pairs = sorted(pair_results.items(), key=lambda x: x[1]["roi_raw"], reverse=True)
    top5_pairs = sorted_pairs[:5]
    worst5_pairs = sorted_pairs[-5:]

    # Single-leg baseline
    sl_roi = ITER39_AGG_ROI

    lines = [
        "# Parlay Execution Backtest — Iter 42",
        f"**Date:** 2026-05-27",
        f"**Data:** `_iter35_merged_2025_26.csv` ({sum(EVAL_ROW_COUNTS.values()):,} stat-rows, 1,119 player-dates)",
        f"**Method:** {n_trials} stochastic trials × per-stat selection rates → avg PnL on real outcomes",
        f"**Excluded pairs:** fg3m+pts (phi=0.513, definitional correlation)",
        "",
        "---",
        "",
        "## Single-Leg Baseline (Iter-39)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total bets | {ITER39_TOTAL_BETS:,} |",
        f"| Aggregate ROI | **+{sl_roi:.2f}%** |",
        f"| Bet direction | OVER only |",
        "",
        "Per-stat hit rates (OVER bets):",
        "",
    ]
    lines.append("| Stat | n_bets | Hit Rate | ROI |")
    lines.append("|------|--------|----------|-----|")
    for stat in ALL_STATS:
        lines.append(
            f"| {stat.upper()} | {ITER39_N_BETS[stat]} | "
            f"{ITER39_HIT_RATE[stat]:.1%} | +{ITER39_ROI_PCT[stat]:.2f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2-Leg Parlay Results",
        "",
        "All OVER parlays: both legs must hit. Odds compounded: dec_A × dec_B.",
        "SGP correction: -15% on parlay payout (sportsbook correlation penalty).",
        "",
        "**Two ROI columns:**",
        "- *Raw odds*: actual market odds from eval CSV (captures real market pricing incl. BLK at +145)",
        "- *Normalized (-110)*: both legs priced at -110, directly comparable to single-leg baseline",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Parlays placed (avg/trial) | {t2['n']:,.0f} |",
        f"| Parlays hit | {t2['hit']:,.0f} ({t2['hit_rate']:.1%}) |",
        f"| Break-even hit rate (-110/-110) | 27.4% |",
        f"| Raw compound ROI (actual odds) | **{t2['roi_raw']:+.2f}%** |",
        f"| Raw SGP-adjusted ROI (-15%) | **{t2['roi_sgp']:+.2f}%** |",
        f"| Normalized ROI (-110 both legs) | **{t2['roi_norm']:+.2f}%** |",
        f"| Normalized SGP-adjusted ROI | **{t2['roi_norm_sgp']:+.2f}%** |",
        f"| vs Single-leg baseline (+{sl_roi:.2f}%) | {'BETTER (norm)' if t2['roi_norm_sgp'] > sl_roi else 'WORSE (norm)'} |",
        "",
        "### 2-Leg: Per-Pair Breakdown (Top 5 by Normalized SGP ROI)",
        "",
        "| Pair | n | Hit Rate | Expected (indep) | Norm ROI (-110) | Norm SGP ROI |",
        "|------|---|----------|-----------------|-----------------|--------------|",
    ]

    sorted_pairs_norm = sorted(pair_results.items(), key=lambda x: x[1]["roi_norm_sgp"], reverse=True)
    top5_pairs_norm = sorted_pairs_norm[:5]

    for pair, pr in top5_pairs_norm:
        a, b = pair
        exp_hit = ITER39_HIT_RATE.get(a, 0.5) * ITER39_HIT_RATE.get(b, 0.5)
        lines.append(
            f"| {a.upper()}+{b.upper()} | {pr['n']:,.0f} | "
            f"{pr['hit_rate']:.1%} | {exp_hit:.1%} | "
            f"{pr['roi_norm']:+.2f}% | {pr['roi_norm_sgp']:+.2f}% |"
        )

    lines += [
        "",
        "### 2-Leg: Per-Pair Breakdown (All Pairs)",
        "",
        "| Pair | n | Hit Rate | Expected (indep) | Raw ROI | Raw SGP | Norm ROI | Norm SGP |",
        "|------|---|----------|-----------------|---------|---------|---------|---------|",
    ]
    for pair, pr in sorted_pairs:
        a, b = pair
        exp_hit = ITER39_HIT_RATE.get(a, 0.5) * ITER39_HIT_RATE.get(b, 0.5)
        lines.append(
            f"| {a.upper()}+{b.upper()} | {pr['n']:,.0f} | "
            f"{pr['hit_rate']:.1%} | {exp_hit:.1%} | "
            f"{pr['roi_raw']:+.2f}% | {pr['roi_sgp']:+.2f}% | "
            f"{pr['roi_norm']:+.2f}% | {pr['roi_norm_sgp']:+.2f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 3-Leg Parlay Results",
        "",
        "All OVER parlays: all 3 legs must hit. Break-even hit rate at -110x3: 14.4%.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Parlays placed (avg/trial) | {t3['n']:,.0f} |",
        f"| Parlays hit | {t3['hit']:,.0f} ({t3['hit_rate']:.1%}) |",
        f"| Break-even hit rate | 14.4% |",
        f"| Raw compound ROI (actual odds) | **{t3['roi_raw']:+.2f}%** |",
        f"| Raw SGP-adjusted ROI | **{t3['roi_sgp']:+.2f}%** |",
        f"| Normalized ROI (-110 all legs) | **{t3['roi_norm']:+.2f}%** |",
        f"| Normalized SGP-adjusted ROI | **{t3['roi_norm_sgp']:+.2f}%** |",
    ]

    # Top 5 triple combos by n (enough volume to be meaningful)
    sorted_triples = sorted(triple_results.items(), key=lambda x: x[1]["n"], reverse=True)
    top_triples = [(k, v) for k, v in sorted_triples if v["n"] >= 10][:5]

    if top_triples:
        lines += [
            "",
            "### 3-Leg: Top Combos by Volume",
            "",
            "| Combo | n | Hit Rate | Raw ROI | SGP ROI |",
            "|-------|---|----------|---------|---------|",
        ]
        for combo, tr in top_triples:
            lines.append(
                f"| {'+'.join(s.upper() for s in combo)} | {tr['n']:,.0f} | "
                f"{tr['hit_rate']:.1%} | {tr['roi_raw']:+.2f}% | {tr['roi_sgp']:+.2f}% |"
            )

    lines += [
        "",
        "---",
        "",
        "## Honest Comparison Table",
        "",
        "Primary comparison uses **normalized -110 odds** to match the single-leg baseline.",
        "Raw odds column shows additional edge from market mispricing (BLK priced at +145 median).",
        "",
        "| Product | Bets/trial | Hit Rate | Norm ROI (-110) | Norm SGP ROI | Raw ROI | vs Baseline |",
        "|---------|-----------|----------|-----------------|--------------|---------|-------------|",
        f"| Single-leg (iter-39) | {ITER39_TOTAL_BETS:,} | ~63.9% avg | +{sl_roi:.2f}% | +{sl_roi:.2f}% | +{sl_roi:.2f}% | baseline |",
        f"| 2-leg parlay | {t2['n']:,.0f} | {t2['hit_rate']:.1%} | {t2['roi_norm']:+.2f}% | {t2['roi_norm_sgp']:+.2f}% | {t2['roi_raw']:+.2f}% | {'↑' if t2['roi_norm_sgp'] > sl_roi else '↓'} |",
        f"| 3-leg parlay | {t3['n']:,.0f} | {t3['hit_rate']:.1%} | {t3['roi_norm']:+.2f}% | {t3['roi_norm_sgp']:+.2f}% | {t3['roi_raw']:+.2f}% | {'↑' if t3['roi_norm_sgp'] > sl_roi else '↓'} |",
        "",
        "Break-even analysis:",
        "",
        "| Parlay | Break-even Hit Rate | Empirical Hit Rate | Edge Margin |",
        "|--------|-------------------|-------------------|-------------|",
        f"| 2-leg (-110/-110) | 27.4% | {t2['hit_rate']:.1%} | {t2['hit_rate']-0.274:+.1%} |",
        f"| 3-leg (-110/-110/-110) | 14.4% | {t3['hit_rate']:.1%} | {t3['hit_rate']-0.144:+.1%} |",
        "",
        "---",
        "",
        "## Ship / No-Ship Recommendation",
        "",
    ]

    # Decision logic — use normalized SGP ROI for comparison to single-leg baseline
    two_leg_positive_norm_sgp = t2["roi_norm_sgp"] > 0
    two_leg_beats_baseline = t2["roi_norm_sgp"] > sl_roi
    three_leg_positive_norm_sgp = t3["roi_norm_sgp"] > 0
    hit_exceeds_breakeven_2 = t2["hit_rate"] > 0.274
    hit_exceeds_breakeven_3 = t3["hit_rate"] > 0.144

    if two_leg_beats_baseline and two_leg_positive_norm_sgp and hit_exceeds_breakeven_2:
        rec = "SHIP 2-LEG PARLAYS"
        rationale = (
            f"2-leg parlays show {t2['roi_norm_sgp']:+.2f}% normalized SGP-adjusted ROI "
            f"(vs +{sl_roi:.2f}% single-leg baseline). "
            f"Empirical hit rate {t2['hit_rate']:.1%} beats break-even 27.4% by "
            f"{t2['hit_rate']-0.274:+.1%}pp. "
            "Positive parlay correlation holds in actual outcome data."
        )
    elif two_leg_positive_norm_sgp and not two_leg_beats_baseline and hit_exceeds_breakeven_2:
        rec = "CONDITIONAL SHIP — 2-leg parlays only"
        rationale = (
            f"2-leg parlays are profitable ({t2['roi_norm_sgp']:+.2f}% norm SGP-adj) but don't beat the "
            f"single-leg baseline (+{sl_roi:.2f}%). Parlays add volume but reduce per-unit ROI. "
            "Use selectively for account diversification."
        )
    elif t2["roi_norm"] > 0 and not two_leg_positive_norm_sgp:
        rec = "NO SHIP — SGP penalty kills edge"
        rationale = (
            f"2-leg parlays are nominally profitable at -110 normalized odds ({t2['roi_norm']:+.2f}%) "
            f"but SGP penalty (-15%) reduces to {t2['roi_norm_sgp']:+.2f}%. "
            "Books absorb the edge via SGP juice reduction."
        )
    else:
        rec = "NO SHIP"
        rationale = (
            f"2-leg parlays at {t2['roi_norm']:+.2f}% norm ROI, {t2['roi_norm_sgp']:+.2f}% norm SGP-adj. "
            f"Hit rate {t2['hit_rate']:.1%} vs 27.4% break-even. "
            "Empirical edge insufficient to justify parlay product."
        )

    lines += [
        f"**Recommendation: {rec}**",
        "",
        f"Rationale: {rationale}",
        "",
        "**3-leg parlays:**",
    ]
    if three_leg_positive_norm_sgp and hit_exceeds_breakeven_3:
        lines.append(
            f"3-leg normalized SGP-adjusted ROI {t3['roi_norm_sgp']:+.2f}% "
            f"with {t3['hit_rate']:.1%} empirical hit rate "
            f"(break-even 14.4%). Volume is thin ({t3['n']:.0f}/trial). "
            "Viable for high-confidence player-games only."
        )
    else:
        hit_str = f"{t3['hit_rate']:.1%}"
        be_note = (
            f"Hit rate {hit_str} above break-even 14.4% — marginal."
            if hit_exceeds_breakeven_3
            else f"Hit rate {hit_str} vs break-even 14.4%."
        )
        lines.append(
            f"3-leg normalized SGP-adjusted ROI {t3['roi_norm_sgp']:+.2f}%. "
            f"{be_note} "
            "Not recommended at current model accuracy."
        )

    lines += [
        "",
        "---",
        "",
        "## Methodology Notes",
        "",
        "- **Bayesian selection:** The production model achieves high hit rates by selecting",
        "  positive-edge rows. Without per-row model predictions, we use Bayes' theorem:",
        "  P(bet|over) = prod_hit_rate * selection_rate / raw_over_rate",
        "  P(bet|under) = (1-prod_hit_rate) * selection_rate / raw_under_rate",
        "  This conditions selection on actual outcome, faithfully reproducing per-stat",
        "  production hit rates while preserving real inter-stat correlation structure.",
        "  STL/BLK have capped probabilities and slightly underestimate true hit rates.",
        "- **Outcome fidelity:** Parlay outcomes use actual `actual_value` vs `closing_line` from",
        "  the eval CSV. No model re-inference required.",
        "- **Odds:** Per-row decimal odds from `over_odds` field; default -110 → 1.909 where missing.",
        "- **SGP penalty:** Flat -15% reduction on net parlay payout. Real penalty varies 10-25%.",
        f"- **Trials:** {n_trials} stochastic trials averaged to reduce sampling variance.",
        f"- **Forbidden pairs:** fg3m+pts excluded from all 2-leg and 3-leg combinations.",
        "- **Pushes:** Excluded from all parlays.",
        "",
        f"*Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}*",
        f"*Script: scripts/iter42_parlay_backtest.py*",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Iter-42 Parlay Execution Backtest")
    print("=" * 60)

    print("\n1. Loading eval data...")
    rows = load_eval_data()
    print(f"   Loaded {len(rows):,} rows")
    from collections import Counter
    stat_dist = Counter(r["stat"] for r in rows)
    for stat in ALL_STATS:
        print(f"   {stat}: {stat_dist[stat]:,} rows")

    print("\n2. Building player-game map...")
    pg_map = build_player_game_map(rows)
    print(f"   {len(pg_map):,} unique player-dates")
    multi_2 = sum(1 for v in pg_map.values() if len(v) >= 2)
    multi_3 = sum(1 for v in pg_map.values() if len(v) >= 3)
    print(f"   {multi_2:,} with 2+ stats, {multi_3:,} with 3+ stats")

    print("\n3. Bayesian selection weights (P_bet_given_over / P_bet_given_under):")
    for stat in ALL_STATS:
        p_o, p_u = BAYESIAN_SEL[stat]
        print(f"   {stat}: P(bet|over)={p_o:.4f}, P(bet|under)={p_u:.4f}, sel_rate={SELECTION_RATES[stat]:.3f}")

    print("\n4. Computing empirical marginal hit rates from eval data...")
    stat_hits: Dict[str, List[bool]] = defaultdict(list)
    for r in rows:
        if not r["push"]:
            stat_hits[r["stat"]].append(r["over_hit"])
    marginal = {
        stat: sum(h) / len(h) if h else 0.0
        for stat, h in stat_hits.items()
    }
    for stat, rate in sorted(marginal.items()):
        print(f"   {stat}: {rate:.3f} (expected from iter39: {ITER39_HIT_RATE.get(stat, 0):.3f})")

    print("\n5. Running parlay simulation (500 trials)...")
    rng = np.random.default_rng(seed=42)
    results = sample_production_bets(pg_map, SELECTION_RATES, rng, n_trials=500)

    t2 = results["total_2leg"]
    t3 = results["total_3leg"]
    print(f"\n   2-leg: {t2['n']:,.0f} parlays/trial, "
          f"hit={t2['hit_rate']:.1%}, "
          f"norm_ROI={t2['roi_norm']:+.2f}%, norm_SGP={t2['roi_norm_sgp']:+.2f}%, "
          f"raw_ROI={t2['roi_raw']:+.2f}%")
    print(f"   3-leg: {t3['n']:,.0f} parlays/trial, "
          f"hit={t3['hit_rate']:.1%}, "
          f"norm_ROI={t3['roi_norm']:+.2f}%, norm_SGP={t3['roi_norm_sgp']:+.2f}%, "
          f"raw_ROI={t3['roi_raw']:+.2f}%")

    print("\n6. Top 5 2-leg pairs by Normalized SGP ROI:")
    sorted_pairs_top = sorted(
        results["pair_results"].items(),
        key=lambda x: x[1]["roi_norm_sgp"],
        reverse=True
    )
    for pair, pr in sorted_pairs_top[:5]:
        print(f"   {pair[0].upper()}+{pair[1].upper()}: "
              f"n={pr['n']:.0f}, hit={pr['hit_rate']:.1%}, "
              f"norm_SGP={pr['roi_norm_sgp']:+.2f}%, raw={pr['roi_raw']:+.2f}%")

    print("\n7. Generating report...")
    os.makedirs(VAULT_STRATEGY_DIR, exist_ok=True)
    report = format_report(results, marginal)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"   Written: {REPORT_PATH}")

    # ── Persist summary to holdout_baseline.json ───────────────────────────────
    baseline_path = os.path.join(
        PROJECT_DIR, "data", "cache", "holdout_baseline.json"
    )
    baseline = {}
    if os.path.exists(baseline_path):
        with open(baseline_path, encoding="utf-8") as fh:
            baseline = json.load(fh)
    baseline["__iter42__"] = {
        "iter": 42,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approach": "parlay_backtest_bayesian_selection_500_trials",
        "n_trials": 500,
        "selection_rates": SELECTION_RATES,
        "2leg": {
            "n_per_trial": round(t2["n"], 1),
            "hit_rate": round(t2["hit_rate"], 4),
            "roi_norm_pct": round(t2["roi_norm"], 2),
            "roi_norm_sgp_pct": round(t2["roi_norm_sgp"], 2),
            "roi_raw_pct": round(t2["roi_raw"], 2),
            "roi_raw_sgp_pct": round(t2["roi_sgp"], 2),
        },
        "3leg": {
            "n_per_trial": round(t3["n"], 1),
            "hit_rate": round(t3["hit_rate"], 4),
            "roi_norm_pct": round(t3["roi_norm"], 2),
            "roi_norm_sgp_pct": round(t3["roi_norm_sgp"], 2),
            "roi_raw_pct": round(t3["roi_raw"], 2),
            "roi_raw_sgp_pct": round(t3["roi_sgp"], 2),
        },
        "single_leg_baseline_roi_pct": ITER39_AGG_ROI,
        "note": (
            "Bayesian selection: P(bet|over/under) conditioned on iter-39 hit rates. "
            "Norm ROI uses -110 both legs for direct baseline comparison. "
            "Raw ROI uses actual CSV odds (BLK median +145 inflates substantially)."
        ),
    }
    baseline["__updated_at__"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(baseline_path, "w", encoding="utf-8") as fh:
        json.dump(baseline, fp=fh, indent=2)
    print(f"   Updated: {baseline_path}")

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Single-leg baseline:             +{ITER39_AGG_ROI:.2f}% ROI")
    print(f"2-leg parlay norm (-110 both):   {t2['roi_norm']:+.2f}% ROI  (hit {t2['hit_rate']:.1%} vs 27.4% BE)")
    print(f"2-leg parlay norm SGP-adj:       {t2['roi_norm_sgp']:+.2f}% ROI")
    print(f"2-leg parlay raw (actual odds):  {t2['roi_raw']:+.2f}% ROI")
    print(f"3-leg parlay norm (-110 all):    {t3['roi_norm']:+.2f}% ROI  (hit {t3['hit_rate']:.1%} vs 14.4% BE)")
    print(f"3-leg parlay norm SGP-adj:       {t3['roi_norm_sgp']:+.2f}% ROI")
    print(f"3-leg parlay raw (actual odds):  {t3['roi_raw']:+.2f}% ROI")
    print()

    if t2["roi_norm_sgp"] > ITER39_AGG_ROI and t2["hit_rate"] > 0.274:
        verdict = "SHIP — parlays beat single-leg even with SGP penalty (norm)"
    elif t2["roi_norm_sgp"] > 0 and t2["hit_rate"] > 0.274:
        verdict = "CONDITIONAL — parlays profitable but don't beat single-leg"
    elif t2["roi_norm"] > 0 and not (t2["roi_norm_sgp"] > 0):
        verdict = "NO SHIP — SGP penalty wipes edge"
    else:
        verdict = "NO SHIP — insufficient empirical edge"
    print(f"Verdict: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
