"""Per-file test for domains.basketball_nba.carryover_asof.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_carryover_asof.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba import carryover_asof as C


def _player_row(game_id, date, season, team, opp, is_home, mins):
    return {"game_id": game_id, "date": date, "season": season, "team": team,
            "opp": opp, "is_home": is_home, "min": mins}


def _synthetic_player_box() -> pd.DataFrame:
    """3 games for team A (2 in 2023-24, 1 in 2024-25) vs a fixed opponent B.
    Game 1: A logs one 35-min player (heavy) -> heavy_min_load=35.
    Game 2 (2 days later, same season): A's carryover feature should see
    game 1's load (35) and rest_days=2. Game 3 is a NEW season -> NaN carryover
    even though only a few days separate the two rows (season reset, not date-gap)."""
    rows = [
        _player_row("G1", "2023-11-01", "2023-24", "A", "B", True, 35.0),
        _player_row("G1", "2023-11-01", "2023-24", "B", "A", False, 10.0),
        _player_row("G2", "2023-11-03", "2023-24", "A", "B", False, 5.0),
        _player_row("G2", "2023-11-03", "2023-24", "B", "A", True, 8.0),
        _player_row("G3", "2024-10-25", "2024-25", "A", "B", True, 40.0),
        _player_row("G3", "2024-10-25", "2024-25", "B", "A", False, 12.0),
    ]
    return pd.DataFrame(rows)


def _build(tmp_path, player_box) -> pd.DataFrame:
    path = C.build_carryover_asof(player_box=player_box, out_path=tmp_path / "out.parquet")
    return pd.read_parquet(path)


def test_first_game_of_season_is_nan(tmp_path):
    out = _build(tmp_path, _synthetic_player_box())
    g1 = out[out["game_id"] == "G1"].iloc[0]
    assert pd.isna(g1["home_heavy_min_load_asof"])  # team A's first game ever
    assert pd.isna(g1["home_rest_days_asof"])


def test_lag1_carries_prior_game_load_and_rest_days(tmp_path):
    out = _build(tmp_path, _synthetic_player_box())
    g2 = out[out["game_id"] == "G2"].iloc[0]
    # A is away in G2; A's carryover = G1's heavy load (35.0), rest = 2 days.
    assert g2["away_heavy_min_load_asof"] == 35.0
    assert g2["away_rest_days_asof"] == 2.0
    # B is home in G2; B's prior game (G1) had no heavy-usage player -> a real 0.0,
    # not NaN (B DID play a prior game, its heavy load was just zero).
    assert g2["home_heavy_min_load_asof"] == 0.0
    assert g2["home_rest_days_asof"] == 2.0


def test_season_boundary_resets_never_bleeds_prior_season(tmp_path):
    out = _build(tmp_path, _synthetic_player_box())
    g3 = out[out["game_id"] == "G3"].iloc[0]
    # A is home in G3 (2024-25) -- must be NaN despite A having 2 prior games in 2023-24.
    assert pd.isna(g3["home_heavy_min_load_asof"])
    assert pd.isna(g3["home_rest_days_asof"])


def test_empty_input_yields_empty_output_columns(tmp_path):
    empty = pd.DataFrame(columns=["game_id", "date", "season", "team", "opp", "is_home", "min"])
    out = _build(tmp_path, empty)
    assert list(out.columns) == C.OUTPUT_COLS
    assert len(out) == 0
