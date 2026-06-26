"""Per-file pytest for prop_cqr.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_prop_cqr.py -q

NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.prop_cqr import (
    _build_leak_free_features,
    _chrono_split,
    _conformity_scores,
    _cqr_band,
    _enforce_non_crossing,
    _per_stat,
    _planted_null_features,
    _predict,
    _split_conformal_band,
    _train_quantile_lgbm,
    run_cqr_gate,
    INSUFFICIENT_DATA,
    _MIN_N,
    _FEATURE_COLS,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_oof_df(
    n_players: int,
    n_games: int,
    stat: str,
    rng: np.random.Generator,
    sigma_lo: float = 3.0,
    sigma_hi: float = 3.0,
    player_sigma_lo: float = 2.0,
    player_sigma_hi: float = 8.0,
) -> pd.DataFrame:
    """Build a synthetic OOF DataFrame.

    When sigma_lo != sigma_hi, odd-numbered players get sigma_lo
    and even-numbered get sigma_hi (two-variance groups).
    """
    rows: List[dict] = []
    base_date = datetime.date(2023, 1, 1)
    for pid in range(n_players):
        player_mean = rng.uniform(5.0, 30.0)
        player_std = rng.uniform(player_sigma_lo, player_sigma_hi)
        noise_std = sigma_lo if (pid % 2 == 0) else sigma_hi
        actuals = rng.normal(player_mean, noise_std, n_games)
        for i, act in enumerate(actuals):
            game_date = base_date + datetime.timedelta(days=i * 3)
            oof_pred = float(player_mean + rng.normal(0.0, player_std * 0.3))
            rows.append({
                "player_id": pid,
                "stat": stat,
                "oof_pred": oof_pred,
                "actual": float(act),
                "game_date": str(game_date),
                "fold": 1,
                "season": "2023-24",
            })
    return pd.DataFrame(rows)


def _make_two_variance_df(n_players: int, n_games: int, rng: np.random.Generator) -> pd.DataFrame:
    """Low-var (sigma=1) and high-var (sigma=10) player groups, same stat."""
    rows: List[dict] = []
    base_date = datetime.date(2023, 1, 1)
    for pid in range(n_players):
        player_mean = rng.uniform(10.0, 20.0)
        noise_std = 1.0 if pid < n_players // 2 else 10.0
        actuals = rng.normal(player_mean, noise_std, n_games)
        for i, act in enumerate(actuals):
            game_date = base_date + datetime.timedelta(days=i * 3)
            rows.append({
                "player_id": pid,
                "stat": "pts",
                "oof_pred": float(player_mean),
                "actual": float(act),
                "game_date": str(game_date),
                "fold": 1,
                "season": "2023-24",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: leak-free features at row 3 == mean of rows 0..2
# ---------------------------------------------------------------------------

def test_features_leak_free():
    """rolling_mean_15 at row index 3 must equal mean(actual[0:3]), not mean(actual[0:4])."""
    rng = np.random.default_rng(1)
    actuals = rng.uniform(5.0, 30.0, 10)
    rows = []
    base = datetime.date(2023, 1, 1)
    for i, a in enumerate(actuals):
        rows.append({
            "player_id": 0,
            "stat": "pts",
            "oof_pred": 10.0,
            "actual": float(a),
            "game_date": str(base + datetime.timedelta(days=i)),
            "fold": 1,
            "season": "2023-24",
        })
    df = pd.DataFrame(rows)
    feat = _build_leak_free_features(df)
    feat = feat.sort_values("game_date").reset_index(drop=True)

    # After dropping n_prior < 5 rows, the first surviving row has n_prior == 5.
    # At that row, rolling_mean_15 should == mean of the 5 prior actuals.
    # The 6th row (index 5 original) has 5 prior games -> rolling_mean_15 = mean(rows 0..4)
    expected_mean = float(np.mean(actuals[:5]))
    first_row = feat.iloc[0]
    assert abs(first_row["rolling_mean_15"] - expected_mean) < 1e-5, (
        f"Expected {expected_mean:.4f}, got {first_row['rolling_mean_15']:.4f}. "
        "rolling_mean_15 should use only rows strictly before the current row."
    )


# ---------------------------------------------------------------------------
# Test 2: n_prior grows strictly within player
# ---------------------------------------------------------------------------

def test_features_n_prior_grows():
    """n_prior must be strictly increasing within each player's sorted games."""
    rng = np.random.default_rng(2)
    df = _make_oof_df(n_players=3, n_games=20, stat="pts", rng=rng)
    feat = _build_leak_free_features(df)
    for pid, grp in feat.groupby("player_id"):
        grp_sorted = grp.sort_values("game_date")
        vals = grp_sorted["n_prior"].to_numpy()
        assert (np.diff(vals) >= 0).all(), (
            f"player {pid}: n_prior not non-decreasing: {vals}"
        )
        # Must be strictly increasing (no duplicates within player after sort)
        if len(vals) > 1:
            assert (np.diff(vals) > 0).all(), (
                f"player {pid}: n_prior has repeated values: {vals}"
            )


# ---------------------------------------------------------------------------
# Test 3: quantile non-crossing after _enforce_non_crossing
# ---------------------------------------------------------------------------

def test_quantile_train_non_crossing():
    """After _enforce_non_crossing, q_lo <= q_hi for all rows."""
    rng = np.random.default_rng(3)
    n = 3000
    X = rng.standard_normal((n, 2))
    # Heteroscedastic: variance grows with X[:,0]
    sigma = 1.0 + np.abs(X[:, 0]) * 2.0
    y = X[:, 0] * 2.0 + rng.standard_normal(n) * sigma

    blo = _train_quantile_lgbm(X, y, 0.05)
    bhi = _train_quantile_lgbm(X, y, 0.95)

    X_test = rng.standard_normal((500, 2))
    qlo = _predict(blo, X_test)
    qhi = _predict(bhi, X_test)
    qlo, qhi = _enforce_non_crossing(qlo, qhi)
    assert (qlo <= qhi).all(), (
        f"After _enforce_non_crossing, {(qlo > qhi).sum()} crossing pairs remain."
    )


# ---------------------------------------------------------------------------
# Test 4: conformity score math
# ---------------------------------------------------------------------------

def test_conformity_scores_math():
    """Manual: y=10 inside [8,12] -> E=-2; y=15 outside -> E=3."""
    q_lo = np.array([8.0, 8.0])
    q_hi = np.array([12.0, 12.0])
    y = np.array([10.0, 15.0])
    E = _conformity_scores(q_lo, q_hi, y)
    assert abs(E[0] - (-2.0)) < 1e-9, f"Expected -2.0, got {E[0]}"
    assert abs(E[1] - 3.0) < 1e-9, f"Expected 3.0, got {E[1]}"


# ---------------------------------------------------------------------------
# Test 5: CQR coverage within 5pp of 90% on synthetic
# ---------------------------------------------------------------------------

def test_cqr_band_coverage_well_calibrated():
    """CQR coverage on a well-calibrated synthetic should be within 5pp of 0.90."""
    rng = np.random.default_rng(5)
    # 30 players x 120 games -> ~3600 rows; after n_prior drop ~3450; ~860 test rows
    df = _make_oof_df(n_players=30, n_games=120, stat="pts", rng=rng)
    result = _per_stat(df, alpha=0.10)
    assert result != INSUFFICIENT_DATA, f"Expected result dict, got {result}"
    assert isinstance(result, dict)
    assert result["n_test"] >= _MIN_N, f"n_test={result['n_test']} < {_MIN_N}"
    gap = abs(result["cqr_coverage"] - 0.90)
    assert gap <= 0.05, (
        f"CQR coverage={result['cqr_coverage']:.4f} deviates from 0.90 by {gap:.4f} (>5pp)"
    )


# ---------------------------------------------------------------------------
# Test 6: CQR width adapts to variance (HIGH-var > 2x LOW-var)
# ---------------------------------------------------------------------------

def test_cqr_width_adapts_to_variance():
    """HIGH-var group (sigma=10) must get > 2x the mean interval width of LOW-var (sigma=1)."""
    rng = np.random.default_rng(6)
    # 40 players: 20 low-var + 20 high-var, 100 games each
    df = _make_two_variance_df(n_players=40, n_games=100, rng=rng)
    import lightgbm as lgb
    from domains.basketball_nba.prop_cqr import (
        _build_leak_free_features, _chrono_split, _FEATURE_COLS,
        _train_quantile_lgbm, _predict, _enforce_non_crossing,
        _conformity_scores, _cqr_band,
    )
    n_players = 40
    alpha = 0.10

    feat = _build_leak_free_features(df)
    df_train, df_calib, df_test = _chrono_split(feat)

    Xtr = df_train[_FEATURE_COLS].to_numpy(dtype=float)
    ytr = df_train["actual"].to_numpy(dtype=float)
    Xcal = df_calib[_FEATURE_COLS].to_numpy(dtype=float)
    ycal = df_calib["actual"].to_numpy(dtype=float)
    Xte = df_test[_FEATURE_COLS].to_numpy(dtype=float)

    blo = _train_quantile_lgbm(Xtr, ytr, alpha / 2.0)
    bhi = _train_quantile_lgbm(Xtr, ytr, 1.0 - alpha / 2.0)

    qlo_cal, qhi_cal = _enforce_non_crossing(_predict(blo, Xcal), _predict(bhi, Xcal))
    E_calib = _conformity_scores(qlo_cal, qhi_cal, ycal)

    qlo_te, qhi_te = _enforce_non_crossing(_predict(blo, Xte), _predict(bhi, Xte))
    lo, hi = _cqr_band(qlo_te, qhi_te, E_calib, alpha)
    widths = hi - lo

    # Low-var: pid < 20, High-var: pid >= 20
    test_pids = df_test["player_id"].to_numpy()
    lo_var_mask = test_pids < n_players // 2
    hi_var_mask = ~lo_var_mask

    if lo_var_mask.sum() < 10 or hi_var_mask.sum() < 10:
        pytest.skip("Not enough test rows per group to evaluate adaptivity")

    mean_lo = float(np.mean(widths[lo_var_mask]))
    mean_hi = float(np.mean(widths[hi_var_mask]))

    assert mean_hi > 2.0 * mean_lo, (
        f"HIGH-var width mean {mean_hi:.3f} should be > 2x LOW-var {mean_lo:.3f}. "
        "CQR should produce wider intervals for noisier players."
    )


# ---------------------------------------------------------------------------
# Test 7: planted null collapses width_std
# ---------------------------------------------------------------------------

def test_planted_null_collapses_width_std():
    """planted_null_collapses must be True on well-calibrated synthetic."""
    rng = np.random.default_rng(7)
    df = _make_oof_df(n_players=30, n_games=120, stat="pts", rng=rng)
    result = _per_stat(df, alpha=0.10)
    if result == INSUFFICIENT_DATA:
        pytest.skip("Insufficient data")
    assert isinstance(result, dict)
    assert result["planted_null_collapses"] is True, (
        f"planted_null_collapses=False: "
        f"cqr_width_mean={result['cqr_width_mean']:.4f}, "
        f"cqr_width_mean_planted={result['cqr_width_mean_planted']:.4f}. "
        "Shuffling features destroys signal, forcing a larger conformal correction "
        "and thus a wider mean band for the null model (> 1.5x real)."
    )


# ---------------------------------------------------------------------------
# Test 8: no forbidden fields in output
# ---------------------------------------------------------------------------

FORBIDDEN = {"pnl", "roi", "edge", "profit", "dollar", "bankroll", "kelly",
             "bet", "wager", "stake"}


def _all_keys_recursive(obj, seen=None):
    """Collect all dict keys recursively."""
    if seen is None:
        seen = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            seen.add(k.lower())
            _all_keys_recursive(v, seen)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _all_keys_recursive(item, seen)
    return seen


def test_no_forbidden_fields():
    """No key in any verdict dict may contain a forbidden term."""
    rng = np.random.default_rng(8)
    df = _make_oof_df(n_players=30, n_games=120, stat="pts", rng=rng)
    result = _per_stat(df, alpha=0.10)
    if result == INSUFFICIENT_DATA:
        pytest.skip("Insufficient data")
    assert isinstance(result, dict)
    keys = _all_keys_recursive(result)
    bad = keys & FORBIDDEN
    assert not bad, f"Forbidden fields found in output: {bad}"


# ---------------------------------------------------------------------------
# Test 9: insufficient data returns sentinel
# ---------------------------------------------------------------------------

def test_insufficient_data_returns_sentinel():
    """Tiny frame (n_test < _MIN_N) must return INSUFFICIENT_DATA, not crash."""
    rng = np.random.default_rng(9)
    # 5 players x 10 games is far too small -> n_test < 200
    df = _make_oof_df(n_players=5, n_games=10, stat="pts", rng=rng)
    result = _per_stat(df, alpha=0.10)
    assert result == INSUFFICIENT_DATA, (
        f"Expected INSUFFICIENT_DATA for tiny frame, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Test 10: run_cqr_gate with missing path returns empty dict
# ---------------------------------------------------------------------------

def test_run_cqr_gate_missing_path_returns_empty():
    """Non-existent OOF path returns empty dict (no crash, no exception)."""
    result = run_cqr_gate(oof_path=Path("nonexistent.parquet"))
    assert isinstance(result, dict)
    assert len(result) == 0, f"Expected empty dict, got {result}"
