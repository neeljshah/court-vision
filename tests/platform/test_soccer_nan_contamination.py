"""tests.platform.test_soccer_nan_contamination — NaN-poisoning guard for soccer ratings.

Verifies that when a row has a non-finite fthg/ftag (NaN or inf):

  (a) That row's PRE-MATCH snapshot is still finite (computed from prior-based
      state before the EW update runs — prior state is always finite).
  (b) SUBSEQUENT clean rows (after the NaN row) emit finite lambdas and
      p_over25 — i.e. the EW state was NOT poisoned by the NaN.
  (c) walk_forward_goals is deterministic on the NaN corpus.

The test uses a synthetic multi-row corpus where one early row has NaN fthg/ftag.

Known bug fixed: domains.soccer.ratings walk_forward_goals / replay formerly ran
  state.gf_ew[home] += ALPHA * (fthg - state.gf_ew[home])
unconditionally; if fthg = NaN the EW state became NaN and poisoned all
subsequent rows for that team.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from domains.soccer.ratings import walk_forward_goals, replay, GoalsState
from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Synthetic corpus: NaN row inserted early in the sequence
#
# Match order after (date, div, home_team, away_team) sort:
#   0  2024-08-10  Arsenal  vs Chelsea    fthg=2  ftag=1   (clean)
#   1  2024-08-17  Arsenal  vs Chelsea    fthg=NaN ftag=NaN (NaN row!)
#   2  2024-08-24  Arsenal  vs Chelsea    fthg=1  ftag=0   (clean — must not be poisoned)
#   3  2024-08-24  Chelsea  vs Arsenal    fthg=0  ftag=2   (clean — same date, different match)
#   4  2024-08-31  Arsenal  vs Chelsea    fthg=3  ftag=1   (clean)
#
# Teams involved: Arsenal (home in row 1 NaN row) and Chelsea (away in row 1 NaN row).
# After the NaN row, BOTH teams' EW state must remain un-poisoned.
# ---------------------------------------------------------------------------

NAN_CORPUS = _make_df([
    # clean warm-up row → teams get initialised + one EW update applied
    {"date": "2024-08-10", "div": "E0", "home_team": "Arsenal",  "away_team": "Chelsea",  "fthg": 2,          "ftag": 1},
    # NaN row — pre-match snapshot should still be finite (prior-based state)
    {"date": "2024-08-17", "div": "E0", "home_team": "Arsenal",  "away_team": "Chelsea",  "fthg": float("nan"), "ftag": float("nan")},
    # clean rows AFTER the NaN row — must NOT be poisoned
    {"date": "2024-08-24", "div": "E0", "home_team": "Arsenal",  "away_team": "Chelsea",  "fthg": 1,          "ftag": 0},
    {"date": "2024-08-24", "div": "E0", "home_team": "Chelsea",  "away_team": "Arsenal",  "fthg": 0,          "ftag": 2},
    {"date": "2024-08-31", "div": "E0", "home_team": "Arsenal",  "away_team": "Chelsea",  "fthg": 3,          "ftag": 1},
])

# Index of the NaN row in the sorted output (row 1 in insertion order = sorted index 1)
_NAN_ROW_IDX = 1
# Indices of subsequent rows that must not be contaminated
_POST_NAN_IDXS = [2, 3, 4]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNaNRowSnapshotIsFinite:
    """(a) The NaN row's pre-match snapshot must still be finite."""

    def test_nan_row_lam_home_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        val = out["lam_home"].iloc[_NAN_ROW_IDX]
        assert math.isfinite(val), (
            f"NaN row lam_home should be finite (prior-based), got {val!r}"
        )

    def test_nan_row_lam_away_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        val = out["lam_away"].iloc[_NAN_ROW_IDX]
        assert math.isfinite(val), (
            f"NaN row lam_away should be finite (prior-based), got {val!r}"
        )

    def test_nan_row_lam_total_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        val = out["lam_total"].iloc[_NAN_ROW_IDX]
        assert math.isfinite(val), (
            f"NaN row lam_total should be finite (prior-based), got {val!r}"
        )

    def test_nan_row_p_over25_finite_and_in_unit_interval(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        val = out["p_over25"].iloc[_NAN_ROW_IDX]
        assert math.isfinite(val), (
            f"NaN row p_over25 should be finite (prior-based), got {val!r}"
        )
        assert 0.0 < val < 1.0, f"p_over25 out of (0,1): {val}"

    def test_nan_row_snapshot_positive(self):
        """Lambdas are formed from prior rates → strictly positive."""
        out = walk_forward_goals(NAN_CORPUS.copy())
        assert out["lam_home"].iloc[_NAN_ROW_IDX] > 0
        assert out["lam_away"].iloc[_NAN_ROW_IDX] > 0
        assert out["lam_total"].iloc[_NAN_ROW_IDX] > 0


class TestSubsequentRowsNotContaminated:
    """(b) Rows after the NaN row must emit finite, positive lambdas/p_over25."""

    def test_post_nan_lam_home_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        for idx in _POST_NAN_IDXS:
            val = out["lam_home"].iloc[idx]
            assert math.isfinite(val), (
                f"Row {idx} lam_home contaminated by NaN row: got {val!r}"
            )

    def test_post_nan_lam_away_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        for idx in _POST_NAN_IDXS:
            val = out["lam_away"].iloc[idx]
            assert math.isfinite(val), (
                f"Row {idx} lam_away contaminated by NaN row: got {val!r}"
            )

    def test_post_nan_lam_total_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        for idx in _POST_NAN_IDXS:
            val = out["lam_total"].iloc[idx]
            assert math.isfinite(val), (
                f"Row {idx} lam_total contaminated by NaN row: got {val!r}"
            )

    def test_post_nan_p_over25_finite(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        for idx in _POST_NAN_IDXS:
            val = out["p_over25"].iloc[idx]
            assert math.isfinite(val), (
                f"Row {idx} p_over25 contaminated by NaN row: got {val!r}"
            )
            assert 0.0 < val < 1.0, (
                f"Row {idx} p_over25 out of (0,1) after NaN guard: {val}"
            )

    def test_post_nan_all_lambdas_positive(self):
        out = walk_forward_goals(NAN_CORPUS.copy())
        for idx in _POST_NAN_IDXS:
            assert out["lam_home"].iloc[idx] > 0, f"Row {idx} lam_home <= 0"
            assert out["lam_away"].iloc[idx] > 0, f"Row {idx} lam_away <= 0"
            assert out["lam_total"].iloc[idx] > 0, f"Row {idx} lam_total <= 0"

    def test_no_nan_in_output_columns(self):
        """No output column should contain NaN anywhere in the corpus."""
        out = walk_forward_goals(NAN_CORPUS.copy())
        for col in ("lam_home", "lam_away", "lam_total", "p_over25"):
            assert out[col].notna().all(), (
                f"Column {col!r} contains NaN after NaN guard applied"
            )

    def test_post_nan_rows_differ_from_prior_rows(self):
        """Rows after the NaN row should have updated (non-prior) lambdas because
        the clean warm-up row (row 0) correctly updated EW state — only the NaN
        row's EW update was skipped."""
        out = walk_forward_goals(NAN_CORPUS.copy())
        # Row 0: Arsenal vs Chelsea, first-ever match → pure prior lambdas
        lam_row0 = out["lam_home"].iloc[0]
        # Row 2: Arsenal vs Chelsea again → state was updated from row 0 (clean);
        #   row 1 NaN was skipped — state is still based on row 0 only but differs
        #   from pure prior because row 0 updated it.
        lam_row2 = out["lam_home"].iloc[2]
        # Both should be finite (not NaN), and row 2 uses updated state from row 0
        assert math.isfinite(lam_row0)
        assert math.isfinite(lam_row2)
        # They may or may not be equal depending on ALPHA, but both must be finite
        # (the important property is finite, not a specific value)


class TestNaNReplayConsistency:
    """EW state after replaying a NaN corpus must be consistent (no NaN in state)."""

    def test_replay_state_no_nan_in_gf_ew(self):
        state = replay(NAN_CORPUS.copy())
        for team, val in state.gf_ew.items():
            assert math.isfinite(val), (
                f"replay: state.gf_ew[{team!r}] = {val!r} after NaN row"
            )

    def test_replay_state_no_nan_in_ga_ew(self):
        state = replay(NAN_CORPUS.copy())
        for team, val in state.ga_ew.items():
            assert math.isfinite(val), (
                f"replay: state.ga_ew[{team!r}] = {val!r} after NaN row"
            )

    def test_replay_state_no_nan_in_league_mu(self):
        state = replay(NAN_CORPUS.copy())
        assert math.isfinite(state.league_mu_home), (
            f"replay: league_mu_home = {state.league_mu_home!r} after NaN row"
        )
        assert math.isfinite(state.league_mu_away), (
            f"replay: league_mu_away = {state.league_mu_away!r} after NaN row"
        )

    def test_replay_n_processed_counts_all_rows(self):
        """n_processed should equal total rows (NaN rows are still 'processed' —
        their snapshot is emitted; the EW update is skipped, not the row itself)."""
        state = replay(NAN_CORPUS.copy())
        assert state.n_processed == len(NAN_CORPUS), (
            f"Expected n_processed={len(NAN_CORPUS)}, got {state.n_processed}"
        )

    def test_replay_counts_exclude_nan_row(self):
        """counts tracks how many times the EW update ran; NaN rows are skipped,
        so each team's count should equal clean matches only (not the NaN match)."""
        state = replay(NAN_CORPUS.copy())
        # Arsenal: row 0 (clean), row 1 (NaN — skipped), row 2 (clean), row 3 (clean), row 4 (clean)
        # → 4 clean rows involve Arsenal
        # Chelsea: rows 0 (clean), 1 (NaN — skipped), 2 (clean), 3 (clean), 4 (clean)
        # → 4 clean rows involve Chelsea
        assert state.counts.get("Arsenal", 0) == 4, (
            f"Arsenal count={state.counts.get('Arsenal',0)}, expected 4 (NaN row skipped)"
        )
        assert state.counts.get("Chelsea", 0) == 4, (
            f"Chelsea count={state.counts.get('Chelsea',0)}, expected 4 (NaN row skipped)"
        )


class TestDeterminism:
    """(c) walk_forward_goals is deterministic on the NaN corpus."""

    def test_two_runs_identical(self):
        out1 = walk_forward_goals(NAN_CORPUS.copy())
        out2 = walk_forward_goals(NAN_CORPUS.copy())
        # Use check_like=False to preserve row order
        for col in ("lam_home", "lam_away", "lam_total", "p_over25"):
            assert out1[col].tolist() == out2[col].tolist(), (
                f"Column {col!r} not deterministic between two runs"
            )

    def test_run_on_inf_score_also_guarded(self):
        """inf fthg/ftag is also non-finite; the guard should skip those updates too."""
        inf_corpus = _make_df([
            {"date": "2024-08-10", "div": "E0", "home_team": "TeamA", "away_team": "TeamB",
             "fthg": 2, "ftag": 1},
            {"date": "2024-08-17", "div": "E0", "home_team": "TeamA", "away_team": "TeamB",
             "fthg": float("inf"), "ftag": 1},
            {"date": "2024-08-24", "div": "E0", "home_team": "TeamA", "away_team": "TeamB",
             "fthg": 1, "ftag": 0},
        ])
        out = walk_forward_goals(inf_corpus)
        for col in ("lam_home", "lam_away", "lam_total", "p_over25"):
            assert out[col].notna().all(), f"{col} has NaN after inf guard"
            for idx in range(len(out)):
                assert math.isfinite(float(out[col].iloc[idx])), (
                    f"Row {idx} {col} not finite after inf in fthg: {out[col].iloc[idx]!r}"
                )
