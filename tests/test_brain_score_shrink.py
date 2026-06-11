"""P3.3 — frozen_score_shrink: between-poll re-price, default no-op, RMSE+bias serve gate.

The headline test DEMONSTRATES the keystone artifact: shrink-toward-current wins MAE but loses RMSE on a
skewed distribution, so the gate (which scores RMSE+bias, never MAE) correctly rejects it -> serve the mean.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame import frozen_score_shrink as fss  # noqa: E402


def test_noop_default_returns_prior_unchanged():
    assert fss.reprice(112.0, 80.0, 0.25, mode="noop") == 112.0


def test_shrink_collapses_to_live_as_game_ends():
    # shrink mode: final -> live score as remaining_frac -> 0 (the shrink-toward-current operation)
    near_end = fss.reprice(112.0, 80.0, 0.01, mode="shrink")
    assert abs(near_end - 80.0) < 1.0          # almost the live score
    start = fss.reprice(112.0, 0.0, 1.0, mode="shrink")
    assert abs(start - 112.0) < 1e-9           # at tip -> the prior projection


def test_rmse_bias_basic():
    rmse, bias, mae = fss.rmse_bias([10.0, 12.0], [11.0, 11.0])
    assert abs(bias - 0.0) < 1e-9              # (-1 + 1)/2
    assert abs(mae - 1.0) < 1e-9
    assert rmse >= mae                         # RMSE >= MAE always


def test_artifact_shrink_wins_mae_loses_rmse():
    """The crux: shrink-toward-current (median) wins MAE but loses RMSE+bias -> gate rejects -> serve mean."""
    v = fss.demonstrate_artifact()
    assert v["median_pred"] < v["mean_pred"]                 # right-skew: median below mean
    assert v["shrink"]["mae"] < v["noop"]["mae"]             # shrink WINS MAE (the seductive trap)
    assert v["shrink"]["rmse"] > v["noop"]["rmse"]           # ... but LOSES RMSE
    assert v["shrink"]["bias"] < 0                           # ... and is negatively biased
    assert v["serve"] == "noop"                              # gate correctly refuses the shrink


def test_gate_accepts_a_genuine_rmse_improvement():
    # if a candidate genuinely lowers RMSE without worsening bias, the gate ships it
    actuals = [10.0, 10.0, 10.0, 10.0]
    noop = [12.0, 12.0, 12.0, 12.0]      # rmse 2, bias +2
    better = [10.5, 9.5, 10.5, 9.5]      # rmse 0.5, bias 0
    v = fss.gate_shrink(better, noop, actuals)
    assert v["serve"] == "shrink" and v["beats_rmse"] and v["not_worse_bias"]
