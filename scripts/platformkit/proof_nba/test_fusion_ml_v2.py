"""Per-file tests for fusion_ml_v2 (pa7 stacked complementary blend).

Run ONLY this file -- full pytest freezes the box.
Run: python -m pytest scripts/platformkit/proof_nba/test_fusion_ml_v2.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.platformkit.proof_nba.fusion_ml_v2 as V2  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _toy_box(n: int = 80, seed: int = 0) -> pd.DataFrame:
    """Synthetic box frame: date-sorted, 4 teams, random scores."""
    rng = np.random.default_rng(seed)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    base_date = pd.Timestamp("2024-11-01")
    rows = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        hp, ap = rng.integers(95, 125), rng.integers(95, 125)
        dt = base_date + pd.Timedelta(days=i // 5)   # ~5 games/day -> dense schedule
        rows.append({"date": dt, "home_abbr": h, "away_abbr": a,
                     "home_pts": float(hp), "away_pts": float(ap)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Unit tests: rest/B2B signal
# ---------------------------------------------------------------------------

def test_rest_b2b_first_game_max_rest():
    """First game ever for each team must be capped at _MAX_REST (no prior game)."""
    df = _toy_box(n=30)
    rest_diff, b2b_net = V2._walk_forward_rest_b2b(df)
    # Both teams appear for the first time in game 0 -> both get _MAX_REST -> diff=0
    assert rest_diff[0] == 0.0
    assert len(rest_diff) == len(df)
    assert np.all(np.isfinite(rest_diff))
    assert np.all(np.isfinite(b2b_net))


def test_rest_b2b_leakfree_update_after():
    """A team playing back-to-back shows negative rest AFTER the first game, not before."""
    rows = [
        {"date": pd.Timestamp("2025-01-01"), "home_abbr": "A", "away_abbr": "B",
         "home_pts": 110.0, "away_pts": 100.0},
        # A plays again the next day (B2B)
        {"date": pd.Timestamp("2025-01-02"), "home_abbr": "C", "away_abbr": "A",
         "home_pts": 105.0, "away_pts": 108.0},
    ]
    df = pd.DataFrame(rows)
    rest_diff, b2b_net = V2._walk_forward_rest_b2b(df)
    # game 0: both teams fresh -> rest_diff = 0
    assert rest_diff[0] == 0.0
    # game 1: A (away) had 1 days_rest = B2B, C is fresh
    # b2b_net = float(C<=1) - float(A<=1) = 0 - 1 = -1 (home team C is NOT on B2B, away A IS)
    assert b2b_net[1] == -1.0


def test_rest_diff_bounded():
    """rest_diff must be in [-_MAX_REST, _MAX_REST] always."""
    df = _toy_box(n=120)
    rest_diff, _ = V2._walk_forward_rest_b2b(df)
    assert np.all(rest_diff >= -V2._MAX_REST)
    assert np.all(rest_diff <= V2._MAX_REST)


def test_b2b_net_values():
    """b2b_net is always in {-1, 0, 1} (indicator difference)."""
    df = _toy_box(n=120)
    _, b2b_net = V2._walk_forward_rest_b2b(df)
    unique = set(b2b_net.tolist())
    assert unique.issubset({-1.0, 0.0, 1.0})


# ---------------------------------------------------------------------------
# Unit tests: win10 signal
# ---------------------------------------------------------------------------

def test_win10_first_game_zero():
    """win10_diff for the first game is 0.0 (both teams start at 0.5 -> diff=0)."""
    df = _toy_box(n=30)
    sig = V2._walk_forward_win10(df)
    assert sig[0] == 0.0
    assert np.all(np.isfinite(sig))


def test_win10_dominant_team_positive():
    """A team winning every game should accumulate positive win10 advantage over opponents."""
    rows = [
        {"date": pd.Timestamp(f"2025-01-{i+1:02d}"),
         "home_abbr": "A", "away_abbr": "B",
         "home_pts": 120.0, "away_pts": 90.0}
        for i in range(15)
    ]
    df = pd.DataFrame(rows)
    sig = V2._walk_forward_win10(df)
    # After several wins, A's win10 > 0.5 and B's < 0.5 -> diff > 0
    assert sig[-1] > 0.0


def test_win10_leakfree_update_after():
    """win10 is updated AFTER the snapshot: early values don't reflect current game result."""
    rows = [
        {"date": pd.Timestamp("2025-01-01"), "home_abbr": "A", "away_abbr": "B",
         "home_pts": 120.0, "away_pts": 90.0},
        {"date": pd.Timestamp("2025-01-02"), "home_abbr": "A", "away_abbr": "B",
         "home_pts": 120.0, "away_pts": 90.0},
    ]
    df = pd.DataFrame(rows)
    sig = V2._walk_forward_win10(df)
    # game 0: no history -> 0.0
    assert sig[0] == 0.0
    # game 1: A updated with 1 win -> A.win10 > 0.5, B.win10 < 0.5 -> sig[1] > 0
    assert sig[1] > 0.0


# ---------------------------------------------------------------------------
# Unit tests: logistic fitter
# ---------------------------------------------------------------------------

def test_logistic_intercept_unpenalised():
    """The logistic must converge on a clearly positive label-rate signal."""
    rng = np.random.default_rng(42)
    x = rng.normal(size=200)
    y = (x + 0.2 * rng.normal(size=200) > 0).astype(float)
    X = np.column_stack([np.ones(200), x])
    w = V2._fit_logistic(X, y)
    assert w[1] > 0.5, "positive feature must get positive weight"


# ---------------------------------------------------------------------------
# Unit tests: WF fuse
# ---------------------------------------------------------------------------

def test_wf_fuse_leakfree_mask():
    """WF fuse emits NaN before _MIN_TRAIN and finite probs in [0,1] after."""
    rng = np.random.default_rng(3)
    n = 200
    elo_logit = rng.normal(scale=0.4, size=n)
    rest_diff = rng.normal(scale=1.5, size=n)
    b2b_net = rng.choice([-1.0, 0.0, 1.0], size=n)
    win10_diff = rng.normal(scale=0.2, size=n)
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-elo_logit))).astype(float)
    fused, valid = V2._walk_forward_fuse(elo_logit, rest_diff, b2b_net, win10_diff, y)
    assert not valid[:V2._MIN_TRAIN].any(), "must be NaN before MIN_TRAIN"
    assert valid[V2._MIN_TRAIN:].all(), "must be valid from MIN_TRAIN onward"
    assert np.all(np.isnan(fused[~valid]))
    fv = fused[valid]
    assert np.all((fv > 0) & (fv < 1)), "probs must be in (0,1)"


def test_wf_fuse_perfect_signal_learns():
    """When elo_logit perfectly predicts y, fused must be similar to elo_prob."""
    rng = np.random.default_rng(7)
    n = 200
    elo_logit = rng.normal(scale=1.0, size=n)
    y = (elo_logit > 0).astype(float)
    rest_diff = rng.normal(scale=0.05, size=n)   # noise
    b2b_net = np.zeros(n)
    win10_diff = rng.normal(scale=0.05, size=n)  # noise
    fused, valid = V2._walk_forward_fuse(elo_logit, rest_diff, b2b_net, win10_diff, y)
    p_elo = 1 / (1 + np.exp(-elo_logit[valid]))
    corr = float(np.corrcoef(fused[valid], p_elo)[0, 1])
    assert corr > 0.90, f"fused should track elo well when elo is nearly perfect (got corr={corr:.3f})"


# ---------------------------------------------------------------------------
# Integration test: run() on real data
# ---------------------------------------------------------------------------

def test_run_contract_keys():
    """run() returns required contract keys; verdict_kind is from the allowed set."""
    rep = V2.run()
    if rep.get("status") != "ok":
        assert rep.get("status") == "data_limited"
        return
    required = {
        "base_brier", "fused_brier", "close_brier",
        "gap_base_to_close", "gap_fused_to_close",
        "gap_narrowed_by_fusion", "fused_minus_base_brier",
        "corr_elo_rest", "corr_elo_b2b", "corr_elo_win10",
        "gate_pass", "verdict_kind", "verdict", "note",
        "n_overlap", "n_holdout",
    }
    missing = required - rep.keys()
    assert not missing, f"Missing keys: {missing}"
    assert rep["verdict_kind"] in {"narrows_gap", "calibration_win", "absorbed_null"}


def test_run_no_dollar_fields():
    """run() must never emit keys containing 'roi', 'pnl', 'profit', or '$'."""
    rep = V2.run()
    lower_keys = [k.lower() for k in rep.keys()]
    for forbidden in ("roi", "pnl", "profit"):
        assert not any(forbidden in k for k in lower_keys), (
            f"Forbidden key pattern '{forbidden}' found in report: {rep.keys()}")
    # no dollar sign anywhere in values
    for v in rep.values():
        if isinstance(v, str):
            assert "$" not in v, f"Dollar sign found in value: {v!r}"


def test_run_gate_logic_consistent():
    """gate_pass must be consistent with fused_brier <= base_brier."""
    rep = V2.run()
    if rep.get("status") != "ok":
        return
    expected = rep["fused_brier"] <= rep["base_brier"] + 1e-6
    assert rep["gate_pass"] == expected, (
        f"gate_pass={rep['gate_pass']} inconsistent with "
        f"fused={rep['fused_brier']} vs base={rep['base_brier']}")


def test_run_rest_signals_complementary():
    """rest_diff and b2b_net must be low-corr with elo_logit (|corr| < 0.5).

    This is the key complementarity check: if corr is high, the signals are
    just Elo relabels and the ABSORB verdict is trivially expected. The test
    passes even on ABSORB; it validates the design choice is correct.
    """
    rep = V2.run()
    if rep.get("status") != "ok":
        return
    assert abs(rep["corr_elo_rest"]) < 0.5, (
        f"rest_diff corr with elo_logit too high: {rep['corr_elo_rest']} "
        f"(signal is not complementary)")
    assert abs(rep["corr_elo_b2b"]) < 0.5, (
        f"b2b_net corr with elo_logit too high: {rep['corr_elo_b2b']} "
        f"(signal is not complementary)")


def test_run_close_at_least_as_sharp_as_base():
    """The devigged close should be at least as sharp as Elo (efficient market sanity check)."""
    rep = V2.run()
    if rep.get("status") != "ok":
        return
    # allow small margin for sampling noise
    assert rep["close_brier"] <= rep["base_brier"] + 0.005, (
        f"close_brier={rep['close_brier']} >> base_brier={rep['base_brier']} "
        f"-- unexpected reversal")
