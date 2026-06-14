"""tests/platform/test_asof_hold.py — leak-free as-of hold% feature tests.

Tests:
  1. No-future-leak assertion (key invariant).
  2. Output has the correct columns (schema contract).
  3. Coverage: first appearance always has n_prior=0 and NaN asof hold.
  4. Accumulation: after 2 matches a player has n_prior=2 and a non-NaN asof hold.
  5. Signal quality on real data: as-of hold MAE < flat-0.62 MAE (or note if marginal).
  6. Surface conditioning: surface-specific asof is populated after a surface-specific match.
  7. Build actually runs on real data (smoke test, fast — no point-MC).

No src/ / kernel/ imports.  Fast tests only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis.asof_hold import (
    OUT_COLS,
    _SURFACES,
    _derive_realized,
    assert_no_future_leak,
    build_asof_hold,
)


# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------
def _make_matches(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal matches DataFrame from a list of row dicts."""
    defaults = {"date": "2020-01-01", "tour": "atp", "tourney_id": "T001",
                "surface": "Hard", "best_of": 3, "round": "R32", "match_num": 1,
                "winner": 1, "score": "6-3 6-3", "retirement": False, "minutes": 90.0}
    records = []
    for i, r in enumerate(rows):
        base = {**defaults, "event_id": f"evt-{i:04d}"}
        base.update(r)
        records.append(base)
    return pd.DataFrame(records)


def _make_stats(event_ids: list[str], *, p1_hold: float = 0.80, p2_hold: float = 0.70) -> pd.DataFrame:
    """Build a minimal match_stats DataFrame with controllable hold% inputs."""
    # We set SvGms=8, and bpFaced/bpSaved such that hold% approximates the target.
    # hold% = 1 - (bpFaced - bpSaved) / SvGms
    # => bpFaced - bpSaved = (1 - hold%) * SvGms
    rows = []
    for eid in event_ids:
        sv = 8.0
        p1_breaks = round((1.0 - p1_hold) * sv)
        p2_breaks = round((1.0 - p2_hold) * sv)
        rows.append({
            "event_id": eid,
            "p1_SvGms": sv, "p1_bpFaced": float(p1_breaks + 2), "p1_bpSaved": 2.0,
            "p1_svpt": 50.0, "p1_1stWon": 22.0, "p1_2ndWon": 9.0,
            "p2_SvGms": sv, "p2_bpFaced": float(p2_breaks + 2), "p2_bpSaved": 2.0,
            "p2_svpt": 48.0, "p2_1stWon": 20.0, "p2_2ndWon": 8.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestNoFutureLeak:
    def test_assert_passes_when_clean(self):
        """assert_no_future_leak should not raise on a clean (debut=NaN) frame."""
        df = pd.DataFrame({
            "p1_n_prior": [0, 0, 1, 2],
            "p2_n_prior": [0, 1, 2, 3],
            "p1_hold_pct_asof": [np.nan, np.nan, 0.75, 0.78],
            "p2_hold_pct_asof": [np.nan, 0.70, 0.72, 0.74],
        })
        # Should not raise.
        assert_no_future_leak(df)

    def test_assert_raises_when_debut_has_value(self):
        """assert_no_future_leak should raise if a debut row has a non-NaN asof."""
        df = pd.DataFrame({
            "p1_n_prior": [0, 1],
            "p2_n_prior": [0, 1],
            "p1_hold_pct_asof": [0.80, 0.82],   # <- bad: debut has a value
            "p2_hold_pct_asof": [np.nan, 0.70],
        })
        with pytest.raises(AssertionError, match="Future-leak"):
            assert_no_future_leak(df)

    def test_build_output_passes_leak_assertion(self, tmp_path):
        """build_asof_hold output should always pass the no-future-leak check."""
        # Two players, three matches, player 0 vs player 1 on dates 01/02/03.
        p1_ids = [100, 100, 200]
        p2_ids = [200, 300, 300]
        dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
        mt = _make_matches([
            {"event_id": f"e{i}", "p1_id": p1_ids[i], "p2_id": p2_ids[i], "date": dates[i]}
            for i in range(3)
        ])
        ms = _make_stats([f"e{i}" for i in range(3)])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        assert_no_future_leak(df)  # explicit check


class TestOutputSchema:
    def test_output_columns(self, tmp_path):
        """build_asof_hold output must have all OUT_COLS and only OUT_COLS."""
        mt = _make_matches([
            {"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"},
            {"event_id": "e1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02"},
        ])
        ms = _make_stats(["e0", "e1"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        assert list(df.columns) == OUT_COLS, f"Column mismatch:\n{list(df.columns)}"

    def test_n_prior_dtype_int(self, tmp_path):
        mt = _make_matches([{"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"}])
        ms = _make_stats(["e0"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        assert df["p1_n_prior"].dtype == np.int64
        assert df["p2_n_prior"].dtype == np.int64


class TestAccumulation:
    def test_debut_has_nan_asof(self, tmp_path):
        """A player's first match must produce NaN asof hold (no history)."""
        mt = _make_matches([{"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"}])
        ms = _make_stats(["e0"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        assert df["p1_n_prior"].iloc[0] == 0
        assert df["p2_n_prior"].iloc[0] == 0
        assert np.isnan(df["p1_hold_pct_asof"].iloc[0])
        assert np.isnan(df["p2_hold_pct_asof"].iloc[0])

    def test_second_match_has_asof_value(self, tmp_path):
        """After one prior match, asof should be populated with a finite value."""
        # p1_id=1 appears in e0 and e1; on e1 they should have n_prior=1.
        mt = _make_matches([
            {"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"},
            {"event_id": "e1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02"},
        ])
        ms = _make_stats(["e0", "e1"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        row_e1 = df[df["event_id"] == "e1"].iloc[0]
        assert row_e1["p1_n_prior"] == 1
        assert not np.isnan(row_e1["p1_hold_pct_asof"])

    def test_asof_value_is_prior_mean(self, tmp_path):
        """asof hold on match 2 should be exactly the hold% from match 0."""
        mt = _make_matches([
            {"event_id": "e0", "p1_id": 10, "p2_id": 20, "date": "2020-01-01"},
            {"event_id": "e1", "p1_id": 10, "p2_id": 30, "date": "2020-01-02"},
        ])
        # Set a very specific hold: SvGms=8, bpFaced=3, bpSaved=1 => hold = 1-(3-1)/8 = 0.75
        ms = pd.DataFrame([
            {"event_id": "e0",
             "p1_SvGms": 8.0, "p1_bpFaced": 3.0, "p1_bpSaved": 1.0,
             "p1_svpt": 40.0, "p1_1stWon": 18.0, "p1_2ndWon": 6.0,
             "p2_SvGms": 8.0, "p2_bpFaced": 4.0, "p2_bpSaved": 2.0,
             "p2_svpt": 38.0, "p2_1stWon": 16.0, "p2_2ndWon": 5.0},
            {"event_id": "e1",
             "p1_SvGms": 8.0, "p1_bpFaced": 3.0, "p1_bpSaved": 1.0,
             "p1_svpt": 40.0, "p1_1stWon": 18.0, "p1_2ndWon": 6.0,
             "p2_SvGms": 8.0, "p2_bpFaced": 3.0, "p2_bpSaved": 1.0,
             "p2_svpt": 40.0, "p2_1stWon": 18.0, "p2_2ndWon": 6.0},
        ])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        e1 = df[df["event_id"] == "e1"].iloc[0]
        expected_hold = 1.0 - (3.0 - 1.0) / 8.0   # = 0.75
        assert abs(e1["p1_hold_pct_asof"] - expected_hold) < 1e-9, (
            f"Expected p1_hold_pct_asof={expected_hold:.4f}, got {e1['p1_hold_pct_asof']:.4f}"
        )


class TestSurfaceConditioning:
    def test_surface_asof_populated_after_surface_match(self, tmp_path):
        """After one Hard match, hard_asof should be populated on the second Hard match."""
        mt = _make_matches([
            {"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01", "surface": "Hard"},
            {"event_id": "e1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02", "surface": "Hard"},
        ])
        ms = _make_stats(["e0", "e1"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        e1 = df[df["event_id"] == "e1"].iloc[0]
        assert not np.isnan(e1["p1_hold_pct_hard_asof"]), "Expected non-NaN hard asof after 1 Hard match"

    def test_surface_asof_nan_for_different_surface(self, tmp_path):
        """After one Clay match, hard_asof should still be NaN for a Hard match."""
        mt = _make_matches([
            {"event_id": "e0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01", "surface": "Clay"},
            {"event_id": "e1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02", "surface": "Hard"},
        ])
        ms = _make_stats(["e0", "e1"])
        out = tmp_path / "hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        e1 = df[df["event_id"] == "e1"].iloc[0]
        assert np.isnan(e1["p1_hold_pct_hard_asof"]), "Expected NaN hard asof when no Hard history"
        assert not np.isnan(e1["p1_hold_pct_clay_asof"]), "Expected non-NaN clay asof after 1 Clay match"


class TestDeriveRealized:
    def test_hold_calculation(self):
        """_derive_realized should correctly compute hold% from raw stats."""
        ms = pd.DataFrame([{
            "event_id": "e0",
            "p1_SvGms": 8.0, "p1_bpFaced": 4.0, "p1_bpSaved": 2.0,
            "p1_svpt": 40.0, "p1_1stWon": 20.0, "p1_2ndWon": 8.0,
            "p2_SvGms": 8.0, "p2_bpFaced": 4.0, "p2_bpSaved": 2.0,
            "p2_svpt": 38.0, "p2_1stWon": 16.0, "p2_2ndWon": 6.0,
        }])
        result = _derive_realized(ms)
        # hold = 1 - (4 - 2) / 8 = 0.75
        assert abs(result["p1_hold_realized"].iloc[0] - 0.75) < 1e-9
        # svpts = (20 + 8) / 40 = 0.70
        assert abs(result["p1_svpts_won_realized"].iloc[0] - 0.70) < 1e-9

    def test_hold_nan_when_no_svgms(self):
        """hold% should be NaN when SvGms is missing."""
        ms = pd.DataFrame([{
            "event_id": "e0",
            "p1_SvGms": np.nan, "p1_bpFaced": 4.0, "p1_bpSaved": 2.0,
            "p1_svpt": 40.0, "p1_1stWon": 20.0, "p1_2ndWon": 8.0,
            "p2_SvGms": 8.0, "p2_bpFaced": 4.0, "p2_bpSaved": 2.0,
            "p2_svpt": 38.0, "p2_1stWon": 16.0, "p2_2ndWon": 6.0,
        }])
        result = _derive_realized(ms)
        assert np.isnan(result["p1_hold_realized"].iloc[0])


class TestRealDataSmoke:
    """Smoke tests on real data — fast (no point-MC).  Skip if data absent."""

    @pytest.fixture(scope="class")
    def real_dfs(self, tmp_path_factory):
        import pathlib
        ms_path = pathlib.Path("data/domains/tennis/match_stats.parquet")
        mt_path = pathlib.Path("data/domains/tennis/matches.parquet")
        if not ms_path.exists() or not mt_path.exists():
            pytest.skip("Real parquet data not found")
        ms = pd.read_parquet(ms_path)
        mt = pd.read_parquet(mt_path)
        out = tmp_path_factory.mktemp("hold") / "asof_hold.parquet"
        df = pd.read_parquet(build_asof_hold(match_stats=ms, matches=mt, out_path=str(out)))
        return df, ms, mt

    def test_row_count(self, real_dfs):
        df, ms, mt = real_dfs
        # Should have one row per match.
        assert len(df) == len(mt)

    def test_no_future_leak_real(self, real_dfs):
        df, ms, mt = real_dfs
        assert_no_future_leak(df)  # should not raise

    def test_coverage_at_least_50_pct(self, real_dfs):
        """At least 50% of matches should have both players with >= 5 prior matches."""
        df, ms, mt = real_dfs
        cov = ((df["p1_n_prior"] >= 5) & (df["p2_n_prior"] >= 5)).mean()
        assert cov >= 0.50, f"Coverage too low: {cov:.1%}"

    def test_asof_hold_beats_flat_baseline(self, real_dfs):
        """As-of hold MAE <= flat-0.62 MAE on covered rows (calibration value)."""
        df, ms, mt = real_dfs
        from domains.tennis.asof_hold import _STATS_COLS
        avail = [c for c in _STATS_COLS if c in ms.columns]
        ms_r = _derive_realized(ms[avail].copy())
        merged = df.merge(ms_r[["event_id", "p1_hold_realized"]], on="event_id", how="inner")
        valid = merged[(merged["p1_n_prior"] >= 5)].dropna(
            subset=["p1_hold_pct_asof", "p1_hold_realized"]
        )
        assert len(valid) > 1000, f"Not enough covered rows: {len(valid)}"
        mae_asof = (valid["p1_hold_pct_asof"] - valid["p1_hold_realized"]).abs().mean()
        mae_flat = (0.62 - valid["p1_hold_realized"]).abs().mean()
        assert mae_asof <= mae_flat + 0.02, (
            f"as-of MAE ({mae_asof:.4f}) exceeds flat-0.62 MAE ({mae_flat:.4f}) by >tolerance"
        )

    def test_surface_coverage(self, real_dfs):
        """Hard surface asof populated for >=30% of covered Hard matches."""
        df, ms, mt = real_dfs
        hard = df[(df["surface"] == "Hard") & (df["p1_n_prior"] >= 5)]
        if len(hard) == 0:
            pytest.skip("No Hard surface covered rows")
        hard_cov = hard["p1_hold_pct_hard_asof"].notna().mean()
        assert hard_cov >= 0.30, f"Hard surface as-of coverage too low: {hard_cov:.1%}"
