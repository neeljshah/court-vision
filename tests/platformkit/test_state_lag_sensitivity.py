"""Per-file smoke tests for scripts/platformkit/benchmarks/crps_market/
state_lag_sensitivity -- exact state-lag recovery + honest distribution/
bucket summaries. Synthetic frames only, no real corpus reads, no network,
no dispatch() calls (those are exercised by the CLI itself, not this file).

Run: python -m pytest tests/platformkit/test_state_lag_sensitivity.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.benchmarks.crps_market.state_lag_sensitivity import (
    _lag_distribution, _scored_bucket, recover_state_lag,
)


def test_recover_state_lag_matches_backward_asof_by_hand():
    candle_ts = pd.Series([100, 130, 200], index=[5, 6, 7])
    states = [{"ts": 90}, {"ts": 125}, {"ts": 195}]
    lag = recover_state_lag(candle_ts, states)
    assert list(lag) == [10.0, 5.0, 5.0]
    assert list(lag.index) == [5, 6, 7]  # original index preserved


def test_recover_state_lag_no_future_leak_never_matches_a_later_state():
    # candle at ts=100 must match the ts=90 state, never the later ts=125 one.
    candle_ts = pd.Series([100])
    states = [{"ts": 90}, {"ts": 125}]
    assert recover_state_lag(candle_ts, states).iloc[0] == 10.0


def test_recover_state_lag_before_first_state_is_honest_nan():
    candle_ts = pd.Series([10, 200])
    lag = recover_state_lag(candle_ts, [{"ts": 100}])
    assert np.isnan(lag.iloc[0])
    assert lag.iloc[1] == 100.0


def test_recover_state_lag_empty_states_is_all_nan_not_zero():
    lag = recover_state_lag(pd.Series([100, 200]), [])
    assert lag.isna().all()


def test_lag_distribution_empty_is_honest_none_not_fabricated_zero():
    assert _lag_distribution(np.array([])) == {
        "n": 0, "mean_s": None, "median_s": None, "p90_s": None, "max_s": None}


def test_lag_distribution_basic_stats():
    d = _lag_distribution(np.array([0.0, 10.0, 20.0, 30.0]))
    assert d["n"] == 4 and d["mean_s"] == 15.0 and d["median_s"] == 15.0 and d["max_s"] == 30.0


def test_scored_bucket_empty_is_underpowered():
    assert _scored_bucket([]) == {"n": 0, "verdict": "UNDERPOWERED"}


def test_scored_bucket_small_n_is_underpowered():
    rows = [{"model_brier": 0.2, "market_brier": 0.21}] * 5
    out = _scored_bucket(rows)
    assert out["verdict"] == "UNDERPOWERED" and out["n"] == 5


def test_scored_bucket_paired_delta_sign_is_market_minus_model():
    # market consistently worse (higher Brier) than model -> positive delta,
    # MODEL_SHARPER once n is large enough to clear the bootstrap-CI bar.
    rng = np.random.default_rng(3)
    rows = [{"model_brier": 0.20 + e, "market_brier": 0.25 + e}
            for e in rng.normal(0, 0.01, size=200)]
    out = _scored_bucket(rows)
    assert out["paired_delta_mean"] > 0
    assert out["verdict"] == "MODEL_SHARPER_PROVISIONAL"
