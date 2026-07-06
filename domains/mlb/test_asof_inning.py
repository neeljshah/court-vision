"""Per-file test for domains.mlb.asof_inning (inning-scoring-shape reclaim).

Acceptance criteria
--------------------
1. build_events_frame: pairs V/H rows correctly (mirrors ingest_sbro), sums
   early (1st-3rd) / late (7th-9th) innings per side, handles 'x' cells as 0.
2. build_asof_inning:
   a. Debut row (0 prior games for a team) -> NaN as-of value (no future leak),
      enforced by the shared walk_forward_asof assertion.
   b. Own-row exclusion: a team's OWN current-game innings never appear in its
      own as-of value for that same row (snapshot strictly precedes update).
   c. Truncation invariance: dropping the tail of events does not change any
      EARLIER row's as-of value (strictly prior-only, no lookahead).
   d. Output columns match OUT_COLS; diff columns are home-away.
3. Atomic write: main() writes via .tmp + os.replace (no partial-file window).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_asof_inning.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from domains.mlb import asof_inning as mod


def _raw_row(date_mmdd: int, rot: int, vh: str, team: str, early: tuple, late: tuple, final: int) -> dict:
    row = {"Date": date_mmdd, "Rot": rot, "VH": vh, "Team": team,
           "1st": early[0], "2nd": early[1], "3rd": early[2],
           "4th": 0, "5th": 0, "6th": 0,
           "7th": late[0], "8th": late[1], "9th": late[2],
           "Final": final}
    return row


def _synthetic_raw() -> pd.DataFrame:
    """4 games, deterministic early/late splits, one 'x' 9th-inning cell (walk-off)."""
    rows = [
        # game 1: 0404 NYY(away) @ BOS(home)
        _raw_row(404, 901, "V", "NYY", (0, 2, 0), (2, 0, 0), 7),
        _raw_row(404, 902, "H", "BOS", (0, 1, 0), (3, 1, "x"), 9),
        # game 2: 0405 PHI(away) @ WAS(home)
        _raw_row(405, 903, "V", "PHI", (0, 0, 0), (4, 0, 0), 11),
        _raw_row(405, 904, "H", "WAS", (1, 0, 0), (0, 0, 0), 1),
        # game 3: 0406 BOS(away) @ NYY(home) -- teams swap sides, history should carry
        _raw_row(406, 905, "V", "BOS", (1, 0, 0), (0, 0, 0), 3),
        _raw_row(406, 906, "H", "NYY", (2, 1, 0), (0, 0, 0), 5),
        # game 4: 0407 WAS(away) @ PHI(home)
        _raw_row(407, 907, "V", "WAS", (0, 0, 0), (0, 0, 0), 0),
        _raw_row(407, 908, "H", "PHI", (0, 1, 0), (0, 0, 0), 2),
    ]
    return pd.DataFrame(rows)


def test_build_events_frame_pairing_and_x_handling():
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    assert len(ev) == 4
    assert set(ev["event_id"]) == {
        "20100404-BOS-NYY-1", "20100405-WAS-PHI-1",
        "20100406-NYY-BOS-1", "20100407-PHI-WAS-1",
    }
    g1 = ev[ev["event_id"] == "20100404-BOS-NYY-1"].iloc[0]
    # away (NYY) early = 0+2+0=2; home (BOS) early = 0+1+0=1
    assert g1["away_early"] == 2.0
    assert g1["home_early"] == 1.0
    # home (BOS) late: 3+1+'x' -> x counts as 0 -> 4.0
    assert g1["home_late"] == 4.0
    assert g1["away_late"] == 2.0


def test_debut_row_is_nan_no_future_leak():
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    out = mod.build_asof_inning(ev)
    g1 = out[out["event_id"] == "20100404-BOS-NYY-1"].iloc[0]
    # both BOS and NYY debut in game 1 -> both sides NaN, n_prior 0
    assert np.isnan(g1["home_early_rate_asof"])
    assert np.isnan(g1["away_early_rate_asof"])
    assert g1["home_innings_n_prior"] == 0
    assert g1["away_innings_n_prior"] == 0


def test_own_row_excluded_history_carries_across_home_away():
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    out = mod.build_asof_inning(ev)
    # game 3: NYY now HOME, after being AWAY in game 1 with early=2.
    # as-of value must be NYY's PRIOR (game-1) early runs, i.e. 2.0 -- NOT influenced
    # by game 3's own away_early(BOS)=1 or home_early(NYY)=3 (own row excluded).
    g3 = out[out["event_id"] == "20100406-NYY-BOS-1"].iloc[0]
    assert g3["home_early_rate_asof"] == 2.0
    assert g3["home_innings_n_prior"] == 1
    # BOS prior early (from game 1, home) = 1.0
    assert g3["away_early_rate_asof"] == 1.0


def test_truncation_invariance_earlier_rows_unchanged():
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    full = mod.build_asof_inning(ev)
    truncated = mod.build_asof_inning(ev.iloc[:-1].reset_index(drop=True))
    common = full[full["event_id"] != "20100407-PHI-WAS-1"].reset_index(drop=True)
    trunc_sorted = truncated.reset_index(drop=True)
    pd.testing.assert_frame_equal(
        common.sort_values("event_id").reset_index(drop=True),
        trunc_sorted.sort_values("event_id").reset_index(drop=True),
    )


def test_output_columns_and_diff_sign():
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    out = mod.build_asof_inning(ev)
    assert list(out.columns) == list(mod.OUT_COLS)
    g3 = out[out["event_id"] == "20100406-NYY-BOS-1"].iloc[0]
    assert g3["early_rate_diff_asof"] == g3["home_early_rate_asof"] - g3["away_early_rate_asof"]
    assert g3["late_rate_diff_asof"] == g3["home_late_rate_asof"] - g3["away_late_rate_asof"]


def test_empty_input_returns_empty_frame_with_columns():
    empty = pd.DataFrame(columns=["event_id", "date", "home_team", "away_team",
                                   "home_early", "away_early", "home_late", "away_late"])
    out = mod.build_asof_inning(empty)
    assert list(out.columns) == list(mod.OUT_COLS)
    assert len(out) == 0


def test_atomic_write_no_partial_file(tmp_path: Path):
    raw = _synthetic_raw()
    ev = mod.build_events_frame(frames=[(2010, raw)])
    out = mod.build_asof_inning(ev)
    out_path = tmp_path / "asof_inning.parquet"
    written = mod._atomic_write_parquet(out, out_path)
    assert written == out_path
    assert out_path.exists()
    assert not out_path.with_suffix(".parquet.tmp").exists()
    reread = pd.read_parquet(str(out_path))
    assert len(reread) == len(out)
