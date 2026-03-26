"""
alt_line_ev_model.py — Alternative prop line EV evaluator.

Given a player's model point estimate + confidence interval (from prop_uncertainty_estimator)
and Pinnacle's current line + odds, fits a normal distribution and computes:
  - P(actual > alt_line) for alt lines in [-2, +2] range
  - EV for each alt line using Pinnacle vig-free odds as benchmark
  - Kelly criterion position size

No train() needed — purely analytical from uncertainty + Pinnacle data.

Public API
----------
    evaluate_alt_lines(player_name, stat, season) -> list[dict]
        -> [{alt_line, direction, model_prob, book_prob, ev, kelly_size}, ...] sorted by ev desc
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# Alt line offsets to evaluate (relative to main line)
_ALT_OFFSETS = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]

# Minimum EV threshold to flag as value
_MIN_EV_THRESHOLD = 0.02

# Standard Pinnacle vig (used as fallback when no odds data)
_PINNACLE_VIG = 0.045


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fit_normal(point_est: float, p25: float, p75: float) -> tuple:
    """
    Fit a normal distribution from point estimate and quantile interval.

    Uses the IQR method: p75 - p25 ≈ 1.349 * sigma (for normal distribution).
    Centers on point estimate.

    Returns (mu, sigma).
    """
    mu = point_est
    iqr = max(p75 - p25, 0.5)  # floor at 0.5 to avoid zero sigma
    sigma = max(iqr / 1.349, 0.5)
    return mu, sigma


def _prob_over_line(mu: float, sigma: float, line: float) -> float:
    """P(X > line) for X ~ N(mu, sigma)."""
    z = (line - mu) / sigma
    return round(1.0 - _norm_cdf(z), 6)


def _american_to_implied(american_odds: int) -> float:
    """Convert American odds to implied probability (with vig)."""
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    else:
        return abs(american_odds) / (abs(american_odds) + 100.0)


def _remove_vig(over_imp: float, under_imp: float) -> tuple:
    """Remove vig from over/under implied probabilities. Returns (vig_free_over, vig_free_under)."""
    total = over_imp + under_imp
    if total <= 0:
        return 0.5, 0.5
    return round(over_imp / total, 6), round(under_imp / total, 6)


def _kelly_size(model_prob: float, book_prob: float, odds_decimal: float,
                bankroll_fraction: float = 0.25) -> float:
    """
    Full Kelly fraction, capped at bankroll_fraction.

    kelly = (model_prob * odds_decimal - 1) / (odds_decimal - 1)
    """
    if odds_decimal <= 1.0 or model_prob <= 0:
        return 0.0
    q = 1.0 - model_prob
    kelly = (model_prob * odds_decimal - 1.0) / (odds_decimal - 1.0)
    # Scale to fractional kelly (0.25 = quarter Kelly)
    kelly = kelly * bankroll_fraction
    return round(max(kelly, 0.0), 4)


def _compute_ev(model_prob: float, book_prob: float) -> float:
    """EV = model_prob / book_prob - 1. Positive = edge over market."""
    if book_prob <= 0:
        return 0.0
    return round(model_prob / book_prob - 1.0, 4)


def evaluate_alt_lines(
    player_name: str,
    stat: str,
    season: str = "2024-25",
    point_estimate: Optional[float] = None,
    p25: Optional[float] = None,
    p75: Optional[float] = None,
    pinnacle_line: Optional[float] = None,
    over_odds: Optional[int] = None,
    under_odds: Optional[int] = None,
) -> list:
    """
    Evaluate EV for alt lines around a player's prop.

    If point_estimate/p25/p75 not provided, fetches from predict_props + predict_uncertainty.
    If pinnacle_line/over_odds not provided, fetches from pinnacle_monitor cache.

    Returns:
        List[{alt_line, direction, model_prob, book_prob, ev, kelly_size}] sorted by ev desc.
    """
    # ── 1. Get point estimate + confidence interval ────────────────────────────
    if point_estimate is None or p25 is None or p75 is None:
        try:
            from src.prediction.player_props import predict_props, _build_player_features
            props = predict_props(player_name, "UNK", season)
            point_estimate = float(props.get(stat, 14.0))

            from src.prediction.prop_uncertainty_estimator import predict_uncertainty
            unc = predict_uncertainty(props.get("features", {}))
            p25 = float(unc.get(f"{stat}_p25", point_estimate * 0.6))
            p75 = float(unc.get(f"{stat}_p75", point_estimate * 1.4))
        except Exception:
            point_estimate = point_estimate or 14.0
            p25 = p25 or point_estimate * 0.6
            p75 = p75 or point_estimate * 1.4

    mu, sigma = _fit_normal(point_estimate, p25, p75)

    # ── 2. Get Pinnacle line + odds ────────────────────────────────────────────
    if pinnacle_line is None:
        try:
            from src.data.pinnacle_monitor import get_prop_signal as _pinnacle
            sig = _pinnacle(player_name, stat)
            pinnacle_line = sig.get("current_line") or sig.get("opening_line")
            over_odds  = sig.get("over_odds",  -110)
            under_odds = sig.get("under_odds", -110)
        except Exception:
            pinnacle_line = None

    if pinnacle_line is None:
        pinnacle_line = point_estimate  # use model estimate as line

    over_odds  = over_odds  or -110
    under_odds = under_odds or -110

    over_imp  = _american_to_implied(int(over_odds))
    under_imp = _american_to_implied(int(under_odds))
    vf_over, vf_under = _remove_vig(over_imp, under_imp)

    # ── 3. Evaluate each alt line offset ──────────────────────────────────────
    results = []
    for offset in _ALT_OFFSETS:
        alt_line = pinnacle_line + offset

        # Over direction
        model_prob_over = _prob_over_line(mu, sigma, alt_line)
        # Adjust book probability for distance from main line
        # Farther alt lines have higher/lower book implied prob
        line_distance = alt_line - pinnacle_line
        if line_distance >= 0:
            # Alt line is higher than main → over is harder → lower book implied prob
            book_prob_over = max(vf_over * (1.0 - 0.12 * line_distance), 0.01)
        else:
            book_prob_over = min(vf_over * (1.0 - 0.08 * line_distance), 0.99)

        ev_over = _compute_ev(model_prob_over, book_prob_over)
        # Decimal odds for kelly: P(win) → decimal = 1 / book_prob
        dec_odds = 1.0 / max(book_prob_over, 0.01)
        kelly_over = _kelly_size(model_prob_over, book_prob_over, dec_odds)

        results.append({
            "alt_line":   round(alt_line, 1),
            "direction":  "over",
            "model_prob": model_prob_over,
            "book_prob":  round(book_prob_over, 4),
            "ev":         ev_over,
            "kelly_size": kelly_over,
        })

        # Under direction
        model_prob_under = round(1.0 - model_prob_over, 6)
        book_prob_under = round(1.0 - book_prob_over, 4)
        ev_under = _compute_ev(model_prob_under, book_prob_under)
        dec_odds_u = 1.0 / max(book_prob_under, 0.01)
        kelly_under = _kelly_size(model_prob_under, book_prob_under, dec_odds_u)

        results.append({
            "alt_line":   round(alt_line, 1),
            "direction":  "under",
            "model_prob": model_prob_under,
            "book_prob":  book_prob_under,
            "ev":         ev_under,
            "kelly_size": kelly_under,
        })

    # Sort by EV descending
    results.sort(key=lambda x: x["ev"], reverse=True)
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("player")
    ap.add_argument("--stat", default="pts")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    rows = evaluate_alt_lines(args.player, args.stat, args.season)
    for row in rows[:5]:
        print(json.dumps(row))
