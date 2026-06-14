"""tests.platform.test_asof_park — Leak-free park factor tests.

Tests:
  1. Correct NaN behavior before min_games threshold.
  2. Correct park factor computation on synthetic data.
  3. No-future-leak assertion: at row i, only rows 0..i-1 contribute.
  4. Round-trip: writes parquet then reads back, columns intact.
  5. League factor = 1.0 when all parks identical.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.mlb.asof_park import build_park_features, OUT_COLS, PARK_MIN_GAMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_BASE = pd.Timestamp("2020-01-01")


def _make_games(n: int, home_runs: int = 5, away_runs: int = 4,
                home_team: str = "AAA", away_team: str = "BBB",
                start_date: pd.Timestamp = _DATE_BASE) -> pd.DataFrame:
    """Create a minimal synthetic games DataFrame for testing."""
    rows = []
    for i in range(n):
        rows.append({
            "event_id": f"game_{i:04d}",
            "date": start_date + pd.Timedelta(days=i),
            "home_team": home_team,
            "away_team": away_team,
            "home_runs": home_runs,
            "away_runs": away_runs,
        })
    return pd.DataFrame(rows)


def _build_in_memory(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Build park features and return the output DataFrame without leaving files."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp = f.name
    try:
        p = build_park_features(games=df, out_path=tmp, **kwargs)
        return pd.read_parquet(str(p))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNanBeforeMinGames:
    """park_total_mean and park_factor are NaN until min_games are observed."""

    def test_all_nan_before_threshold(self):
        """With min_games=5, first 4 rows must be NaN."""
        df = _make_games(12, min_games_unused=None)
        out = _build_in_memory(df, min_games=5)
        # first 4 rows: park_n_prior < 5 → NaN
        assert out["park_n_prior"].iloc[:4].max() < 5
        assert out["park_total_mean"].iloc[:4].isna().all(), \
            "park_total_mean must be NaN before min_games"
        assert out["park_factor"].iloc[:4].isna().all(), \
            "park_factor must be NaN before min_games"

    def test_non_nan_after_threshold(self):
        """After min_games prior games, values must be finite."""
        df = _make_games(20, min_games_unused=None)
        out = _build_in_memory(df, min_games=5)
        # row index 5 → 5 prior games observed → non-NaN
        assert pd.notna(out["park_total_mean"].iloc[5]), \
            "park_total_mean should be non-NaN once min_games are met"
        assert pd.notna(out["park_factor"].iloc[5]), \
            "park_factor should be non-NaN once min_games are met"

    def test_park_n_prior_is_zero_initially(self):
        df = _make_games(5)
        out = _build_in_memory(df, min_games=3)
        assert out["park_n_prior"].iloc[0] == 0, "First game has 0 prior games"
        assert out["park_n_prior"].iloc[1] == 1
        assert out["park_n_prior"].iloc[2] == 2


# Strip unused kwarg from _make_games calls above
def _make_games(n: int, home_runs: int = 5, away_runs: int = 4,
                home_team: str = "AAA", away_team: str = "BBB",
                start_date: pd.Timestamp = _DATE_BASE,
                **_ignored) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "event_id": f"game_{i:04d}",
            "date": start_date + pd.Timedelta(days=i),
            "home_team": home_team,
            "away_team": away_team,
            "home_runs": home_runs,
            "away_runs": away_runs,
        })
    return pd.DataFrame(rows)


class TestCorrectComputation:
    """park_total_mean equals the correct prior mean of total_runs."""

    def test_constant_runs_gives_constant_mean(self):
        """If every game has the same total, mean must equal that total."""
        home_runs, away_runs = 5, 3  # total = 8
        df = _make_games(20, home_runs=home_runs, away_runs=away_runs)
        out = _build_in_memory(df, min_games=5)

        valid = out[out["park_total_mean"].notna()]
        assert len(valid) > 0, "Expected some valid rows"
        # All valid park means should be exactly 8.0
        assert np.allclose(valid["park_total_mean"].values, 8.0), \
            "park_total_mean should equal 8.0 (constant total)"

    def test_park_n_prior_increments(self):
        """park_n_prior must equal the row index (one home game per row)."""
        df = _make_games(15, home_team="XYZ")
        out = _build_in_memory(df, min_games=1)
        for i in range(len(out)):
            assert out["park_n_prior"].iloc[i] == i, \
                f"Row {i}: expected n_prior={i}, got {out['park_n_prior'].iloc[i]}"

    def test_mean_updates_correctly(self):
        """Manual check: alternating totals, verify running mean."""
        rows = []
        for i in range(10):
            rows.append({
                "event_id": f"g{i}",
                "date": _DATE_BASE + pd.Timedelta(days=i),
                "home_team": "AAA",
                "away_team": "BBB",
                # totals: 0, 10, 0, 10, 0, 10, 0, 10, 0, 10
                "home_runs": 0 if i % 2 == 0 else 5,
                "away_runs": 0 if i % 2 == 0 else 5,
            })
        df = pd.DataFrame(rows)
        out = _build_in_memory(df, min_games=2)

        # Row index 2 (3rd game): 2 prior games (totals 0, 10) → mean = 5.0
        assert pd.notna(out["park_total_mean"].iloc[2]), "Row 2 should be non-NaN"
        assert abs(out["park_total_mean"].iloc[2] - 5.0) < 1e-9, \
            f"Expected mean 5.0 at row 2, got {out['park_total_mean'].iloc[2]}"

        # Row index 4 (5th game): 4 prior games (0,10,0,10) → mean = 5.0
        assert abs(out["park_total_mean"].iloc[4] - 5.0) < 1e-9, \
            f"Expected mean 5.0 at row 4, got {out['park_total_mean'].iloc[4]}"

    def test_two_separate_parks(self):
        """Games at two different parks must track independent histories."""
        # Park A: total=10 every game; Park B: total=6 every game
        rows = []
        for i in range(16):
            # Alternate between parks A and B each day
            is_a = i % 2 == 0
            rows.append({
                "event_id": f"g{i}",
                # Use different times so sort is deterministic
                "date": _DATE_BASE + pd.Timedelta(hours=i * 25),
                "home_team": "AAA" if is_a else "BBB",
                "away_team": "CCC",
                "home_runs": 6 if is_a else 3,
                "away_runs": 4 if is_a else 3,
            })
        df = pd.DataFrame(rows)
        out = _build_in_memory(df, min_games=3)

        # Park AAA rows: total always 10
        aaa_rows = out[out["event_id"].isin(
            [f"g{i}" for i in range(16) if i % 2 == 0]
        )]
        valid_aaa = aaa_rows[aaa_rows["park_total_mean"].notna()]
        assert len(valid_aaa) > 0
        assert np.allclose(valid_aaa["park_total_mean"].values, 10.0), \
            "Park AAA should have mean=10"

        # Park BBB rows: total always 6
        bbb_rows = out[out["event_id"].isin(
            [f"g{i}" for i in range(16) if i % 2 == 1]
        )]
        valid_bbb = bbb_rows[bbb_rows["park_total_mean"].notna()]
        assert len(valid_bbb) > 0
        assert np.allclose(valid_bbb["park_total_mean"].values, 6.0), \
            "Park BBB should have mean=6"


class TestNoFutureLeak:
    """CRITICAL: at row i, only games 0..i-1 for that home_team can contribute."""

    def test_no_future_leak(self):
        """Exhaustive check: rebuild per-row from scratch, compare to module output."""
        n = 30
        home_runs = np.arange(n, dtype=float)
        away_runs = np.ones(n, dtype=float)
        rows = []
        for i in range(n):
            rows.append({
                "event_id": f"g{i:03d}",
                "date": _DATE_BASE + pd.Timedelta(days=i),
                "home_team": "PARK",
                "away_team": "OPP",
                "home_runs": int(home_runs[i]),
                "away_runs": int(away_runs[i]),
            })
        df = pd.DataFrame(rows)
        out = _build_in_memory(df, min_games=1)

        # Reconstruct expected means row by row using ONLY prior data
        total = home_runs + away_runs
        for i in range(n):
            prior_totals = total[:i]  # strictly prior
            expected_n = len(prior_totals)
            assert out["park_n_prior"].iloc[i] == expected_n, \
                f"Row {i}: expected n_prior={expected_n}, got {out['park_n_prior'].iloc[i]}"

            if expected_n >= 1:
                expected_mean = float(prior_totals.mean())
                actual_mean = out["park_total_mean"].iloc[i]
                assert pd.notna(actual_mean), f"Row {i}: mean should be non-NaN"
                assert abs(actual_mean - expected_mean) < 1e-9, \
                    f"Row {i}: expected mean={expected_mean:.6f}, got {actual_mean:.6f}"
            else:
                assert pd.isna(out["park_total_mean"].iloc[i]), \
                    f"Row {i}: should be NaN with 0 prior games"

    def test_future_total_not_in_feature(self):
        """If we change the LAST game's total, earlier row features must be unchanged."""
        df_original = _make_games(15)
        df_modified = _make_games(15)
        # Change the last game's runs drastically
        df_modified.loc[df_modified.index[-1], "home_runs"] = 99
        df_modified.loc[df_modified.index[-1], "away_runs"] = 99

        out_orig = _build_in_memory(df_original, min_games=3)
        out_mod = _build_in_memory(df_modified, min_games=3)

        # All but the last row's features must be identical (future data changed only
        # the last game, so rows 0..n-2 must be unchanged).
        for col in ("park_total_mean", "park_factor", "park_n_prior"):
            orig_vals = out_orig[col].values[:-1]
            mod_vals = out_mod[col].values[:-1]
            # Handle NaN comparison
            nan_match = pd.isna(orig_vals) == pd.isna(mod_vals)
            assert nan_match.all(), \
                f"NaN pattern differs in {col} for rows 0..n-2 (future leak!)"
            valid = ~pd.isna(orig_vals)
            if valid.any():
                assert np.allclose(orig_vals[valid], mod_vals[valid], atol=1e-9), \
                    f"Values differ in {col} for rows 0..n-2 (future leak!)"


class TestOutputSchema:
    """Output columns, dtypes, and round-trip parquet integrity."""

    def test_output_columns_present(self):
        df = _make_games(15)
        out = _build_in_memory(df, min_games=5)
        for col in OUT_COLS:
            assert col in out.columns, f"Missing column: {col}"

    def test_event_id_matches_input(self):
        df = _make_games(10)
        out = _build_in_memory(df, min_games=3)
        assert set(out["event_id"].tolist()) == set(df["event_id"].tolist()), \
            "event_id set mismatch between input and output"

    def test_park_n_prior_dtype(self):
        df = _make_games(10)
        out = _build_in_memory(df, min_games=3)
        assert out["park_n_prior"].dtype == np.int32, \
            "park_n_prior must be int32"

    def test_round_trip_parquet(self):
        """Write to temp parquet, read back, verify columns intact."""
        df = _make_games(20)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp = f.name
        try:
            p = build_park_features(games=df, out_path=tmp, min_games=5)
            rt = pd.read_parquet(str(p))
            for col in OUT_COLS:
                assert col in rt.columns, f"Round-trip missing column: {col}"
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


class TestFactorBehavior:
    """park_factor = park_mean / league_mean; homogeneous parks => factor ~ 1.0."""

    def test_identical_parks_give_factor_near_one(self):
        """When all parks have the same scoring environment, factor must be ~1.0."""
        # 2 parks, same total every game (8)
        rows = []
        for i in range(40):
            park = "AAA" if i % 2 == 0 else "BBB"
            rows.append({
                "event_id": f"g{i:03d}",
                "date": _DATE_BASE + pd.Timedelta(hours=i * 25),
                "home_team": park,
                "away_team": "CCC",
                "home_runs": 4,
                "away_runs": 4,
            })
        df = pd.DataFrame(rows)
        out = _build_in_memory(df, min_games=5)
        valid = out[out["park_factor"].notna()]
        assert len(valid) > 0
        assert np.allclose(valid["park_factor"].values, 1.0, atol=1e-9), \
            "Identical parks should yield factor=1.0"

    def test_high_scoring_park_factor_gt_one(self):
        """A consistently high-scoring park should have factor > 1."""
        # ParkHigh: total=12; ParkLow: total=6 → league mean converges ~9
        # ParkHigh factor should converge above 1.0
        rows = []
        for i in range(60):
            is_high = i % 2 == 0
            rows.append({
                "event_id": f"g{i:03d}",
                "date": _DATE_BASE + pd.Timedelta(hours=i * 25),
                "home_team": "HIGH" if is_high else "LOW",
                "away_team": "MID",
                "home_runs": 7 if is_high else 3,
                "away_runs": 5 if is_high else 3,
            })
        df = pd.DataFrame(rows)
        out = _build_in_memory(df, min_games=5)

        high_ids = {f"g{i:03d}" for i in range(60) if i % 2 == 0}
        valid_high = out[out["event_id"].isin(high_ids) & out["park_factor"].notna()]
        assert len(valid_high) > 0
        # All valid HIGH park factors should be > 1.0
        assert (valid_high["park_factor"].values > 1.0).all(), \
            "High-scoring park should consistently have factor > 1"
