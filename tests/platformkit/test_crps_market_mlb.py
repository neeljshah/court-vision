"""Per-file smoke tests for scripts/platformkit/benchmarks/crps_market -- the
join logic (back-to-back-series ambiguity regression) and the market Gaussian
fit (single-line fallback + degenerate-sigma regression). No network, no real
corpus reads -- synthetic frames only.

Run: python -m pytest tests/platformkit/test_crps_market_mlb.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.benchmarks.crps_market.market_dist import (
    devig_points, fit_market_gaussian,
)
from scripts.platformkit.benchmarks.crps_market.mlb_join import build_game_join


def _statcast_games(rows):
    return pd.DataFrame(rows, columns=["game_pk", "game_date", "pair_key", "realized_total"])


def _line_totals(rows):
    df = pd.DataFrame(rows, columns=["game_id", "home", "away", "commence_time"])
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True)
    return df


def test_join_exact_day_match():
    sg = _statcast_games([(101, dt.date(2026, 6, 18), "BOS|TOR", 8)])
    lt = _line_totals([("g1", "Boston Red Sox", "Toronto Blue Jays",
                         "2026-06-18T17:35:00Z")])
    join = build_game_join(sg, lt)
    assert join == {"g1": 101}


def test_join_back_to_back_series_never_falsely_ambiguous():
    """Regression: two BOS@TOR games on consecutive days must NOT make the
    exact-day match ambiguous just because a day-1 fallback candidate also
    exists (this was the original bug -- union of both dates over-matched)."""
    sg = _statcast_games([
        (101, dt.date(2026, 6, 17), "BOS|TOR", 5),
        (102, dt.date(2026, 6, 18), "BOS|TOR", 8),
    ])
    lt = _line_totals([("g1", "Boston Red Sox", "Toronto Blue Jays",
                         "2026-06-18T17:35:00Z")])
    join = build_game_join(sg, lt)
    assert join == {"g1": 102}


def test_join_utc_rollover_uses_prior_day_fallback():
    """Exact commence date has no candidate -> falls back to the day before."""
    sg = _statcast_games([(101, dt.date(2026, 6, 17), "BOS|TOR", 8)])
    lt = _line_totals([("g1", "Boston Red Sox", "Toronto Blue Jays",
                         "2026-06-18T02:10:00Z")])
    join = build_game_join(sg, lt)
    assert join == {"g1": 101}


def test_devig_points_dedups_and_averages_by_line():
    rows = [
        {"line": 8.5, "side": "over", "devigged_prob": 0.50},
        {"line": 8.5, "side": "under", "devigged_prob": 0.52},
        {"line": 8.5, "side": "over", "devigged_prob": 0.48},
    ]
    pts = devig_points(rows)
    assert pts == [(8.5, pytest.approx((0.50 + (1 - 0.52) + 0.48) / 3))]


def test_fit_market_gaussian_single_line_uses_fallback_sigma():
    mu, sigma, n_used = fit_market_gaussian([(8.5, 0.5)], sigma_fallback=4.5)
    assert n_used == 1
    assert sigma == pytest.approx(4.5)
    assert mu == pytest.approx(8.5, abs=0.05)  # p_over==0.5 -> line is the median


def test_fit_market_gaussian_degenerate_two_point_falls_back():
    """Regression: two near-collinear points must NOT produce a blown-up sigma
    (this was the original bug -- an unbounded least-squares fit gave sigma>100
    for total-runs, an implausible market-implied spread)."""
    mu, sigma, n_used = fit_market_gaussian(
        [(9.5, 0.4981), (10.0, 0.4967)], sigma_fallback=4.5)
    assert n_used == 1
    assert sigma == pytest.approx(4.5)


def test_fit_market_gaussian_well_separated_points_recovers_market_fit():
    from scipy.stats import norm
    true_mu, true_sigma = 8.0, 4.5
    lines = [6.0, 8.0, 10.0]
    points = [(x, float(1 - norm.cdf(x, true_mu, true_sigma))) for x in lines]
    mu, sigma, n_used = fit_market_gaussian(points, sigma_fallback=4.5)
    assert n_used == 3
    assert mu == pytest.approx(true_mu, abs=0.1)
    assert sigma == pytest.approx(true_sigma, abs=0.1)
