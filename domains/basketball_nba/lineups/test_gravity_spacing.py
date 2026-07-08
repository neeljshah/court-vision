"""Per-file test: build_gravity's floor/formula on a small synthetic on/off
frame (no floor-sized real fixture exists in a single game), and
build_spacing's math on the real 0022500003.json fixture's actual shot
locations (lowered min_shots since one game can't clear the production
20-shot-per-lineup floor for every lineup, but easily clears it for the
starters' longest stint).

Run: python -m pytest domains/basketball_nba/lineups/test_gravity_spacing.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.lineups.gravity_spacing import build_gravity, build_spacing, load_shot_events_xy
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, build_game_stints

_FIXTURE = _PBP_DIR / "0022500003.json"


def test_gravity_proxy_formula_and_floor() -> None:
    on_off_df = pd.DataFrame([
        # clears both floors -> kept, gravity_proxy = 0.55 - 0.50 = 0.05
        {"player_id": 1, "team_id": 100, "player_name": "A", "n_games": 20, "min_on": 500.0,
         "teammate_efg_on": 0.55, "teammate_efg_off": 0.50, "teammate_fga_on": 300, "teammate_fga_off": 250},
        # fails min_on floor -> dropped
        {"player_id": 2, "team_id": 100, "player_name": "B", "n_games": 5, "min_on": 50.0,
         "teammate_efg_on": 0.60, "teammate_efg_off": 0.40, "teammate_fga_on": 300, "teammate_fga_off": 250},
        # fails teammate_fga_off floor -> dropped
        {"player_id": 3, "team_id": 100, "player_name": "C", "n_games": 20, "min_on": 500.0,
         "teammate_efg_on": 0.60, "teammate_efg_off": 0.40, "teammate_fga_on": 300, "teammate_fga_off": 50},
    ])
    result = build_gravity(on_off_df)
    assert len(result) == 1
    assert result.iloc[0]["player_id"] == 1
    assert abs(result.iloc[0]["gravity_proxy"] - 0.05) < 1e-9


@pytest.mark.skipif(not _FIXTURE.exists() or not _BOX_SRC.exists(), reason="local-only data not present")
def test_spacing_positive_on_real_fixture() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    box_df = pd.read_parquet(_BOX_SRC)
    stints, notes = build_game_stints(game_json, box_df)
    assert notes == []
    stints_df = pd.DataFrame(stints)

    shots_xy_df = load_shot_events_xy(game_json)
    assert {"x", "y"}.issubset(shots_xy_df.columns)
    shots_xy_df = attach_lineup_to_shots(stints_df, shots_xy_df)

    result = build_spacing(stints_df, shots_xy_df, min_shots=5)
    assert len(result) > 0
    assert (result["n_shots"] >= 5).all()
    assert (result["spacing_mean_dist"] > 0).all()
