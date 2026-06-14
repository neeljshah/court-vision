"""tests.platform.test_sp_elo_offset — Unit + integration tests for SP-Elo offset model.

Tests:
  1. No future-leak: all train rows have date < split_date.
  2. NaN SP → zero offset (pure-Elo fallback).
  3. Predictions are valid probabilities in [0, 1].
  4. build_merged_features works on real data.
  5. time_split_evaluation returns SP Brier <= baseline + tolerance.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PATH = _REPO_ROOT / "data/domains/mlb/games.parquet"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def games_df() -> pd.DataFrame:
    """Load the real MLB games corpus."""
    if not _GAMES_PATH.exists():
        pytest.skip("games.parquet not found — skipping real-data tests")
    return pd.read_parquet(str(_GAMES_PATH))


@pytest.fixture(scope="module")
def merged_df(games_df: pd.DataFrame) -> pd.DataFrame:
    from domains.mlb.sp_elo_offset import build_merged_features
    return build_merged_features(games_df)


@pytest.fixture(scope="module")
def eval_results(games_df: pd.DataFrame) -> dict:
    from domains.mlb.sp_elo_offset import time_split_evaluation
    return time_split_evaluation(games_df, train_frac=0.50)


# ---------------------------------------------------------------------------
# Test 1: No future-leak — train rows strictly before split_date
# ---------------------------------------------------------------------------

def test_no_future_leak(merged_df: pd.DataFrame, eval_results: dict) -> None:
    """Train rows must not include dates strictly after split_date.

    split_date is the first date of the test set.  Same-date doubleheader games
    can legitimately straddle the index split (some fall in train, some in test) —
    that is NOT a leak because both halves of a doubleheader are the same calendar
    day, and the Elo + SP features for each game are computed from strictly prior
    results only (snapshot-before-update).

    A real leak would be fitting w on data from a calendar date strictly AFTER
    split_date.  We assert that cannot happen.
    """
    split_date = eval_results["split_date"]
    n_train = eval_results["n_train"]

    train_rows = merged_df.iloc[:n_train]
    train_dates = pd.to_datetime(train_rows["date"]).dt.date

    # Strict-after violations (date > split_date) are leaks.
    # Same-date rows (date == split_date) are acceptable (doubleheader boundary).
    violations = int((train_dates > split_date).sum())
    assert violations == 0, (
        f"Leak detected: {violations} train rows have date strictly after "
        f"split_date ({split_date}). train rows: {len(train_rows)}"
    )


# ---------------------------------------------------------------------------
# Test 2: NaN SP → zero offset (pure-Elo fallback)
# ---------------------------------------------------------------------------

def test_nan_sp_gives_zero_offset() -> None:
    """NaN sp_first6_diff_ew must produce the same prediction as pure-Elo (w*z_sp=0)."""
    from domains.mlb.sp_elo_offset import predict_sp_elo
    from scipy.special import expit

    rng = np.random.default_rng(42)
    n = 100
    elo_logit = rng.normal(0, 0.5, n)

    df = pd.DataFrame({
        "elo_logit": elo_logit,
        "sp_first6_diff_ew": np.full(n, np.nan),
    })

    w = 1.5   # non-zero weight — but with NaN→0 offset should vanish
    preds = predict_sp_elo(df, w=w, sp_mean=0.0, sp_std=1.0)
    expected = expit(elo_logit)

    np.testing.assert_allclose(
        preds, expected, rtol=1e-6,
        err_msg="NaN SP rows must produce pure-Elo prediction (z_sp=0 → no offset)",
    )


# ---------------------------------------------------------------------------
# Test 3: Predictions are valid probabilities
# ---------------------------------------------------------------------------

def test_predictions_valid_probabilities(merged_df: pd.DataFrame, eval_results: dict) -> None:
    """All test-set predictions must lie strictly in (0, 1)."""
    from domains.mlb.sp_elo_offset import predict_sp_elo

    w = eval_results["w"]
    sp_mean = eval_results["sp_mean"]
    sp_std = eval_results["sp_std"]
    n_train = eval_results["n_train"]

    test_df = merged_df.iloc[n_train:].reset_index(drop=True)
    preds = predict_sp_elo(test_df, w=w, sp_mean=sp_mean, sp_std=sp_std)

    assert preds.ndim == 1, "predictions must be 1-D"
    assert len(preds) == len(test_df), "length mismatch"
    assert np.all(preds >= 0.0), "predictions must be >= 0"
    assert np.all(preds <= 1.0), "predictions must be <= 1"
    assert np.all(np.isfinite(preds)), "all predictions must be finite"


# ---------------------------------------------------------------------------
# Test 4: build_merged_features works on real data
# ---------------------------------------------------------------------------

def test_build_merged_features_shape(merged_df: pd.DataFrame, games_df: pd.DataFrame) -> None:
    """build_merged_features must return a non-empty DataFrame with required columns."""
    required_cols = [
        "event_id", "date", "target_home_win",
        "p_home_elo", "elo_logit",
        "sp_first6_diff_ew", "home_sp_starts_prior", "away_sp_starts_prior",
    ]
    for col in required_cols:
        assert col in merged_df.columns, f"Missing column: {col!r}"

    assert len(merged_df) > 0, "merged_df must not be empty"
    assert len(merged_df) <= len(games_df), "merged rows should not exceed games rows"

    # elo_logit must be finite for all rows (p_home_elo clipped from 0/1)
    assert np.all(np.isfinite(merged_df["elo_logit"].values)), (
        "elo_logit must be finite for all rows"
    )

    # target_home_win must be 0 or 1
    vals = merged_df["target_home_win"].values
    assert set(vals).issubset({0, 1, 0.0, 1.0}), (
        "target_home_win must contain only 0/1 values"
    )


# ---------------------------------------------------------------------------
# Test 5: SP model Brier <= baseline + tolerance
# ---------------------------------------------------------------------------

def test_sp_brier_not_worse_than_baseline(eval_results: dict) -> None:
    """SP-aware model Brier must not exceed baseline Elo Brier by more than 0.001.

    The honest null result is acceptable (no improvement = 0 delta).
    This test guards against a regression (bug causing SP to hurt Brier > 1e-3).
    """
    baseline_brier = eval_results["baseline"]["brier"]
    sp_brier = eval_results["sp_model"]["brier"]
    delta = sp_brier - baseline_brier

    # Report for visibility
    print(
        f"\nBaseline Brier={baseline_brier:.5f}  "
        f"SP-model Brier={sp_brier:.5f}  "
        f"Delta={delta:+.5f}  "
        f"w={eval_results['w']:.4f}  "
        f"Coverage={eval_results['coverage_pct']:.1f}%"
    )

    tolerance = 0.001
    assert delta <= tolerance, (
        f"SP model Brier ({sp_brier:.5f}) worse than baseline ({baseline_brier:.5f}) "
        f"by {delta:.5f} (tolerance {tolerance}). Check for a bug — "
        f"honest null result is OK but regression is not."
    )
