"""tests/platform/test_asof_hold_wta.py -- leak-free WTA as-of hold% feature tests.

Mirrors tests/platform/test_asof_hold.py exactly, for the WTA companion.

Tests:
  1. No-future-leak assertion (key invariant) -- future match cannot change a past row.
  2. Output has the correct columns (schema contract).
  3. Coverage: first appearance always has n_prior=0 and NaN asof hold.
  4. Accumulation: after 1 prior match a player has n_prior=1 and a non-NaN asof hold.
  5. WTA-tag filter: _filter_wta_stats keeps only "-wta-" event_ids.
  6. Build actually runs on real data (smoke test, fast -- no point-MC).

No src/ / kernel/ imports.  Fast tests only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis.asof_hold import _derive_realized
from domains.tennis.asof_hold_wta import (
    OUT_COLS,
    _filter_wta_stats,
    assert_no_future_leak,
    build_asof_hold_wta,
)


# ---------------------------------------------------------------------------
# Synthetic fixture builders (WTA-tagged event_ids)
# ---------------------------------------------------------------------------
def _make_wta_matches(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal wta_matches DataFrame from a list of row dicts."""
    defaults = {"date": "2020-01-01", "tour": "wta", "tourney_id": "T001",
                "surface": "Hard", "best_of": 3, "round": "R32", "match_num": 1,
                "winner": 1, "score": "6-3 6-3", "retirement": False, "minutes": 90.0}
    records = []
    for i, r in enumerate(rows):
        base = {**defaults, "event_id": f"2020{i:04d}-wta-T001-evt-{i:04d}"}
        base.update(r)
        records.append(base)
    return pd.DataFrame(records)


def _make_stats(event_ids: list[str], *, p1_hold: float = 0.80, p2_hold: float = 0.70) -> pd.DataFrame:
    """Build a minimal match_stats DataFrame with controllable hold% inputs.

    hold% = 1 - (bpFaced - bpSaved) / SvGms
    """
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
class TestWtaTagFilter:
    def test_filter_keeps_only_wta_rows(self):
        ms = pd.DataFrame({
            "event_id": [
                "20200101-wta-T1-1-2-1",
                "20200101-atp-T1-1-2-1",
                "20200102-wta-T2-3-4-2",
            ],
        })
        out = _filter_wta_stats(ms)
        assert len(out) == 2
        assert all("-wta-" in eid for eid in out["event_id"])

    def test_filter_empty_when_no_wta_rows(self):
        ms = pd.DataFrame({"event_id": ["20200101-atp-T1-1-2-1"]})
        out = _filter_wta_stats(ms)
        assert len(out) == 0


class TestNoFutureLeak:
    def test_build_output_passes_leak_assertion(self, tmp_path):
        """build_asof_hold_wta output should always pass the no-future-leak check."""
        p1_ids = [100, 100, 200]
        p2_ids = [200, 300, 300]
        dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
        eids = [f"2020010{i+1}-wta-T1-{p1_ids[i]}-{p2_ids[i]}-{i}" for i in range(3)]
        mt = _make_wta_matches([
            {"event_id": eids[i], "p1_id": p1_ids[i], "p2_id": p2_ids[i], "date": dates[i]}
            for i in range(3)
        ])
        ms = _make_stats(eids)
        out = tmp_path / "hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=mt, out_path=str(out)))
        assert_no_future_leak(df)  # explicit check

    def test_future_match_cannot_change_a_past_row(self, tmp_path):
        """The key as-of property: appending a FUTURE match must not alter any
        already-emitted PAST row's asof feature values (strict as-of joins only)."""
        p1_ids = [100, 100]
        p2_ids = [200, 300]
        dates = ["2020-01-01", "2020-01-02"]
        eids = [f"2020010{i+1}-wta-T1-{p1_ids[i]}-{p2_ids[i]}-{i}" for i in range(2)]
        mt_base = _make_wta_matches([
            {"event_id": eids[i], "p1_id": p1_ids[i], "p2_id": p2_ids[i], "date": dates[i]}
            for i in range(2)
        ])
        ms_base = _make_stats(eids)
        out1 = tmp_path / "base.parquet"
        df_base = pd.read_parquet(
            build_asof_hold_wta(match_stats=ms_base, wta_matches=mt_base, out_path=str(out1))
        )

        # Append a FUTURE 3rd match (later date, same players) with DIFFERENT hold values.
        eid3 = "20200103-wta-T1-100-200-2"
        mt_future = pd.concat([mt_base, _make_wta_matches(
            [{"event_id": eid3, "p1_id": 100, "p2_id": 200, "date": "2020-01-03"}]
        )], ignore_index=True)
        ms_future = pd.concat(
            [ms_base, _make_stats([eid3], p1_hold=0.30, p2_hold=0.95)], ignore_index=True
        )
        out2 = tmp_path / "future.parquet"
        df_future = pd.read_parquet(
            build_asof_hold_wta(match_stats=ms_future, wta_matches=mt_future, out_path=str(out2))
        )

        # The first two rows (by event_id) must be BIT-IDENTICAL across both builds.
        base_sorted = df_base.sort_values("event_id").reset_index(drop=True)
        future_prefix = df_future[df_future["event_id"].isin(eids)].sort_values(
            "event_id").reset_index(drop=True)
        pd.testing.assert_frame_equal(base_sorted, future_prefix, check_like=False)


class TestOutputSchema:
    def test_output_columns(self, tmp_path):
        """build_asof_hold_wta output must have all OUT_COLS (shared w/ ATP) and only OUT_COLS."""
        mt = _make_wta_matches([
            {"event_id": "20200101-wta-T1-1-2-0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"},
            {"event_id": "20200102-wta-T1-1-3-1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02"},
        ])
        ms = _make_stats(["20200101-wta-T1-1-2-0", "20200102-wta-T1-1-3-1"])
        out = tmp_path / "hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=mt, out_path=str(out)))
        assert list(df.columns) == OUT_COLS, f"Column mismatch:\n{list(df.columns)}"

    def test_n_prior_dtype_int(self, tmp_path):
        mt = _make_wta_matches([{"event_id": "20200101-wta-T1-1-2-0", "p1_id": 1, "p2_id": 2,
                                  "date": "2020-01-01"}])
        ms = _make_stats(["20200101-wta-T1-1-2-0"])
        out = tmp_path / "hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=mt, out_path=str(out)))
        assert df["p1_n_prior"].dtype == np.int64
        assert df["p2_n_prior"].dtype == np.int64


class TestAccumulation:
    def test_debut_has_nan_asof(self, tmp_path):
        mt = _make_wta_matches([{"event_id": "20200101-wta-T1-1-2-0", "p1_id": 1, "p2_id": 2,
                                  "date": "2020-01-01"}])
        ms = _make_stats(["20200101-wta-T1-1-2-0"])
        out = tmp_path / "hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=mt, out_path=str(out)))
        assert df["p1_n_prior"].iloc[0] == 0
        assert df["p2_n_prior"].iloc[0] == 0
        assert np.isnan(df["p1_hold_pct_asof"].iloc[0])
        assert np.isnan(df["p2_hold_pct_asof"].iloc[0])

    def test_second_match_has_asof_value(self, tmp_path):
        mt = _make_wta_matches([
            {"event_id": "20200101-wta-T1-1-2-0", "p1_id": 1, "p2_id": 2, "date": "2020-01-01"},
            {"event_id": "20200102-wta-T1-1-3-1", "p1_id": 1, "p2_id": 3, "date": "2020-01-02"},
        ])
        ms = _make_stats(["20200101-wta-T1-1-2-0", "20200102-wta-T1-1-3-1"])
        out = tmp_path / "hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=mt, out_path=str(out)))
        row_e1 = df[df["event_id"] == "20200102-wta-T1-1-3-1"].iloc[0]
        assert row_e1["p1_n_prior"] == 1
        assert not np.isnan(row_e1["p1_hold_pct_asof"])


class TestRealDataSmoke:
    """Smoke tests on real on-disk data -- fast, skip if data absent."""

    @pytest.fixture(scope="class")
    def real_dfs(self, tmp_path_factory):
        import pathlib
        ms_path = pathlib.Path("data/domains/tennis/match_stats.parquet")
        wm_path = pathlib.Path("data/domains/tennis/wta_matches.parquet")
        if not ms_path.exists() or not wm_path.exists():
            pytest.skip("Real parquet data not found")
        ms = pd.read_parquet(ms_path)
        wm = pd.read_parquet(wm_path)
        out = tmp_path_factory.mktemp("hold_wta") / "asof_hold_wta.parquet"
        df = pd.read_parquet(build_asof_hold_wta(match_stats=ms, wta_matches=wm, out_path=str(out)))
        return df, ms, wm

    def test_row_count(self, real_dfs):
        df, ms, wm = real_dfs
        assert len(df) == len(wm)

    def test_no_future_leak_real(self, real_dfs):
        df, ms, wm = real_dfs
        assert_no_future_leak(df)  # should not raise

    def test_coverage_at_least_50_pct(self, real_dfs):
        """At least 50% of matches should have both players with >= 5 prior matches."""
        df, ms, wm = real_dfs
        cov = ((df["p1_n_prior"] >= 5) & (df["p2_n_prior"] >= 5)).mean()
        assert cov >= 0.50, f"Coverage too low: {cov:.1%}"
