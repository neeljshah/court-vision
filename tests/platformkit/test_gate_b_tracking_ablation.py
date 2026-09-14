"""tests.platformkit.test_gate_b_tracking_ablation -- Q06 (Gate B) deliverable checks.
No network.

(a) join_prior_season never returns a row from the game's own season (it must pick the
    PRIOR-season table row, ignoring a same-season row for the same player if present).
(b) load_tracking_family's defender_matchup columns never include a realized_* label column.
(c) ceiling_verdict on three CI cases (excludes-0-favour / excludes-0-against / contains-0).
(d) build_challenger_frame returns the same rows in the same order as the input frame, plus
    the tracking columns, on a synthetic fixture.

Run: python -m pytest tests/platformkit/test_gate_b_tracking_ablation.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.proof_nba.gate_b_tracking_ablation import (
    build_challenger_frame, ceiling_verdict, join_prior_season, load_tracking_family)


def _synthetic_champion_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 1, 2, 2],
        "season": ["2023-24", "2024-25", "2023-24", "2024-25"],
        "game_id": ["g1", "g2", "g3", "g4"],
        "date": pd.to_datetime(["2023-11-01", "2024-11-01", "2023-11-02", "2024-11-02"]),
    })


def _synthetic_family() -> dict:
    tracking = pd.DataFrame({
        "player_id": [1, 1, 2],
        "season": ["2023-24", "2024-25", "2023-24"],
        "player_name": ["a", "a", "b"],
        "drives": [5.0, 9.0, 3.0],
    })
    hustle = pd.DataFrame({
        "player_id": [1, 2],
        "season": ["2023-24", "2023-24"],
        "player_name": ["a", "b"],
        "hustle_deflections": [1.0, 2.0],
    })
    dmatch = pd.DataFrame({
        "player_id": [1, 2],
        "game_id": ["g2", "g4"],
        "def_test_asof": [0.4, 0.6],
        "def_n_prior": [3, 5],
        "realized_points_allowed": [22.0, 18.0],  # must never be loaded by the real module
    })
    return {"tracking": tracking, "hustle": hustle, "defender_matchup": dmatch,
            "dm_cols": ["def_test_asof", "def_n_prior"]}


def test_prior_season_join_ignores_same_season_row():
    df = _synthetic_champion_frame()
    fam = _synthetic_family()
    merged, cols, _ = join_prior_season(df, fam["tracking"], "trk")
    row_2024 = merged[(merged["player_id"] == 1) & (merged["season"] == "2024-25")].iloc[0]
    # player 1's 2024-25 row must pick up the 2023-24 (prior-season) drives value (5.0), not
    # the 2024-25 table row's own value (9.0) even though both exist in the source table.
    assert row_2024["trk_drives"] == 5.0
    # player 1's 2023-24 row has no 2022-23 data on disk -> must be NaN, not a same-season fallback.
    row_2023 = merged[(merged["player_id"] == 1) & (merged["season"] == "2023-24")].iloc[0]
    assert pd.isna(row_2023["trk_drives"])
    assert cols == ["trk_drives"]


def test_defender_matchup_never_loads_realized_columns():
    fam = load_tracking_family()
    assert not any(c.startswith("realized_") for c in fam["dm_cols"])
    assert not any(c.startswith("realized_") for c in fam["defender_matchup"].columns)
    assert all(c.endswith("_asof") or c == "def_n_prior" for c in fam["dm_cols"])


def test_ceiling_verdict_three_cases():
    assert ceiling_verdict({"ci_lo": 0.01, "ci_hi": 0.05}) == "CEILING_POSITIVE"
    assert ceiling_verdict({"ci_lo": -0.05, "ci_hi": -0.01}) == "CEILING_NEGATIVE"
    assert ceiling_verdict({"ci_lo": -0.02, "ci_hi": 0.03}) == "CEILING_ZERO"


def test_challenger_frame_same_rows_same_order_plus_tracking_cols():
    df = _synthetic_champion_frame()
    fam = _synthetic_family()
    df2, trk_cols, hus_cols, dm_cols = build_challenger_frame(df, fam)
    assert len(df2) == len(df)
    assert df2["player_id"].tolist() == df["player_id"].tolist()
    assert df2["game_id"].tolist() == df["game_id"].tolist()
    assert df2["season"].tolist() == df["season"].tolist()
    for c in trk_cols + hus_cols + dm_cols:
        assert c in df2.columns
    assert "realized_points_allowed" not in df2.columns
    # defender_matchup joined on (player_id, game_id) directly -- g2 belongs to player 1.
    g2 = df2[df2["game_id"] == "g2"].iloc[0]
    assert g2["def_test_asof"] == 0.4
