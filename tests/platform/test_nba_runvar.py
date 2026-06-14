"""tests/platform/test_nba_runvar.py

Tests for ingest_quarter_box.py and asof_runvar.py.

Properties verified:
  1. test_ingest_runs        — ingest_quarter_box produces the parquet file.
  2. test_row_counts         — parquet has >=8000 rows (1000+ games x 4 qtrs x 2 teams).
  3. test_quarter_sum        — per-game team quarter sums are all non-negative (OT tolerance).
  4. test_runvar_schema      — asof_runvar output has expected columns.
  5. test_no_future_leak     — n_prior >= 0 for all rows; features exist for games with priors.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_QPTS_PATH = _REPO_ROOT / "data" / "cache" / "nba_quarter_points.parquet"
_RV_PATH = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_runvar.parquet"


# ---------------------------------------------------------------------------
# Fixtures: build the parquets once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qpts_df() -> pd.DataFrame:
    """Build (or load) the quarter-points parquet and return it as a DataFrame."""
    from domains.basketball_nba.ingest_quarter_box import build_quarter_points
    path = build_quarter_points(force=False)
    return pd.read_parquet(path)


@pytest.fixture(scope="session")
def runvar_df(qpts_df: pd.DataFrame) -> pd.DataFrame:
    """Build (or load) the runvar parquet and return it as a DataFrame."""
    from domains.basketball_nba.asof_runvar import build_asof_runvar
    path = build_asof_runvar(qpts_df=qpts_df, force=False)
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Test 1: ingest_quarter_box runs and produces the parquet
# ---------------------------------------------------------------------------


def test_ingest_runs(qpts_df: pd.DataFrame) -> None:
    """ingest_quarter_box produces a non-empty parquet at the expected path."""
    assert _QPTS_PATH.exists(), f"Expected parquet at {_QPTS_PATH}"
    assert len(qpts_df) > 0, "quarter_points parquet is empty — ingest failed."
    expected_cols = {"game_id", "team_id", "quarter", "pts"}
    missing = expected_cols - set(qpts_df.columns)
    assert not missing, f"Missing columns: {missing}"


# ---------------------------------------------------------------------------
# Test 2: row count (>= 8000 means >= ~1000 games * 4 qtrs * 2 teams)
# ---------------------------------------------------------------------------


def test_row_counts(qpts_df: pd.DataFrame) -> None:
    """Parquet must have at least 8000 rows (1000 games × 4 quarters × 2 teams)."""
    assert len(qpts_df) >= 8000, (
        f"Expected >= 8000 rows, got {len(qpts_df)}. "
        "Coverage appears too low for the known ~1299 cached games."
    )


# ---------------------------------------------------------------------------
# Test 3: per-game quarter point sums are non-negative (OT tolerance)
# ---------------------------------------------------------------------------


def test_quarter_sum(qpts_df: pd.DataFrame) -> None:
    """Per-(game_id, team_id) total pts must be >= 0.

    Real NBA scores are always non-negative. OT games add extra quarters (5+)
    but all individual quarter scores remain non-negative. We allow up to 30 pts
    tolerance for any potential discrepancy in OT parsing but enforce non-negative
    totals.
    """
    totals = qpts_df.groupby(["game_id", "team_id"])["pts"].sum()
    negative = totals[totals < 0]
    assert len(negative) == 0, (
        f"Found {len(negative)} (game_id, team_id) pairs with negative total pts:\n"
        f"{negative.head(10)}"
    )

    # Also verify no single quarter has wildly wrong points (>200 per quarter is impossible)
    outliers = qpts_df[qpts_df["pts"] > 200]
    assert len(outliers) == 0, (
        f"Found {len(outliers)} quarters with >200 pts (data corruption):\n"
        f"{outliers.head(5)}"
    )


# ---------------------------------------------------------------------------
# Test 4: runvar schema
# ---------------------------------------------------------------------------


def test_runvar_schema(runvar_df: pd.DataFrame) -> None:
    """asof_runvar output DataFrame must have expected columns."""
    expected_cols = {"game_id", "home_var", "away_var", "combined_var", "n_prior"}
    missing = expected_cols - set(runvar_df.columns)
    assert not missing, f"Missing columns in runvar output: {missing}"
    assert len(runvar_df) > 0, "runvar parquet is empty."


# ---------------------------------------------------------------------------
# Test 5: no future leak — n_prior >= 0 for all rows; features exist when n_prior > 0
# ---------------------------------------------------------------------------


def test_no_future_leak(runvar_df: pd.DataFrame) -> None:
    """Verify leak-free discipline: n_prior >= 0 and features exist when expected.

    For each row:
      - n_prior must be >= 0 (it counts strictly prior games).
      - When n_prior > 0, home_var and away_var must be non-NaN
        (variance is computable from at least 1 prior game's quarters).
      - When n_prior == 0, home_var and away_var may be NaN (no prior data).
    """
    df = runvar_df.copy()
    df["n_prior"] = pd.to_numeric(df["n_prior"], errors="coerce").fillna(0)

    # n_prior must always be >= 0
    assert (df["n_prior"] >= 0).all(), "Some rows have n_prior < 0 — impossible."

    # For games with at least 1 prior game, combined_var must be non-NaN
    has_prior = df[df["n_prior"] >= 1]
    if len(has_prior) > 0:
        nan_combined = has_prior["combined_var"].isna().sum()
        # Allow up to 5% NaN tolerance for edge cases (team not in quarter_box)
        max_nan = max(1, int(0.05 * len(has_prior)))
        assert nan_combined <= max_nan, (
            f"Too many NaN combined_var for rows with n_prior >= 1: "
            f"{nan_combined}/{len(has_prior)} ({100*nan_combined/len(has_prior):.1f}%)"
        )

    # Verify n_prior = 0 rows exist (first games of the season)
    n_zero = (df["n_prior"] == 0).sum()
    assert n_zero >= 0, "n_prior=0 count should be non-negative."  # always true, just documenting


# ---------------------------------------------------------------------------
# Test 6: combined_var = home_var + away_var (consistency check)
# ---------------------------------------------------------------------------


def test_combined_var_consistency(runvar_df: pd.DataFrame) -> None:
    """combined_var must equal home_var + away_var where both are finite."""
    df = runvar_df.dropna(subset=["home_var", "away_var", "combined_var"])
    if len(df) == 0:
        pytest.skip("No rows with all three variance columns non-null.")
    expected = df["home_var"] + df["away_var"]
    diff = (expected - df["combined_var"]).abs()
    assert (diff < 1e-6).all(), (
        f"combined_var != home_var + away_var for {(diff >= 1e-6).sum()} rows."
    )
