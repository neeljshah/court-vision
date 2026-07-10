"""Per-file test for interaction_factory.builders_carryover. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_carryover.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.interaction_factory import builders_carryover as bc


def test_mlb_diff_col_strips_asof_suffix():
    assert bc._mlb_diff_col("sp_prior_pitch_count_asof") == "sp_prior_pitch_count_diff_asof"


def test_mlb_carryover_source_for_year_points_at_the_right_parquet():
    p = bc.mlb_carryover_source_for_year("2024")
    assert p.name == "carryover_asof__2024.parquet"
    assert p.parent.name == "mlb"


def _mlb_games_current(n=40):
    rng = np.random.default_rng(5)
    dates = pd.date_range("2024-04-01", periods=n, freq="D")
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": dates, "season": 2024, "game_seq": np.arange(n),
        "home_team": [f"T{i % 6}" for i in range(n)],
        "away_team": [f"T{(i + 2) % 6}" for i in range(n)],
        "home_runs": rng.integers(0, 8, n), "away_runs": rng.integers(0, 8, n),
        "target_home_win": rng.integers(0, 2, n).astype(float),
    })


def test_build_mlb_carryover_frame_merges_diff_and_elo(monkeypatch):
    gc = _mlb_games_current()
    asof = pd.DataFrame({
        "event_id": gc["event_id"].iloc[:-1],  # last game's carryover row absent
        "sp_prior_pitch_count_diff_asof": np.linspace(-10, 10, len(gc) - 1),
    })
    out = bc.build_mlb_carryover_frame(["sp_prior_pitch_count_asof"], asof, games_current=gc)
    assert {"asof__sp_prior_pitch_count_asof", "p_base", "y"} <= set(out.columns)
    # inner-joined on event_id -- the absent carryover row must not appear
    assert len(out) == len(gc) - 1
    assert out["p_base"].between(0.0, 1.0).all()


def test_build_mlb_carryover_frame_drops_rows_without_target_home_win():
    """Failure mode: a games_current row with a NaN target_home_win (game not
    yet final) must be excluded from the training frame, never silently
    treated as a valid label."""
    gc = _mlb_games_current(10)
    gc.loc[0, "target_home_win"] = np.nan
    asof = pd.DataFrame({
        "event_id": gc["event_id"],
        "sp_prior_pitch_count_diff_asof": np.linspace(-5, 5, len(gc)),
    })
    out = bc.build_mlb_carryover_frame(["sp_prior_pitch_count_asof"], asof, games_current=gc)
    assert gc.loc[0, "event_id"] not in set(out["event_id"])
    assert len(out) == len(gc) - 1
