"""Per-file test: zone mapping + aggregation formulas on a small synthetic
shot set, plus a smoke pass over one real game fixture.

Run: python -m pytest domains/basketball_nba/composition/test_concession_profiles.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.composition.concession_profiles import (
    aggregate_concession, load_game_fta, load_game_shots,
)
from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_nba.lineups.pbp_lineups import _PBP_DIR

_FIXTURE = _PBP_DIR / "0022500003.json"


def test_aggregate_concession_formulas() -> None:
    # Defense 200 faces 4 shots from offense 100: 2 rim makes (1 assisted),
    # 1 rim miss, 1 corner3 make unassisted, 1 fastbreak rim make.
    shots = pd.DataFrame([
        {"game_id": "g1", "offense_team_id": 100, "defense_team_id": 200, "zone": "rim",
         "made": 1, "is_3": 0, "fgm": 1, "fg3m": 0, "assisted": 1, "fastbreak": 0},
        {"game_id": "g1", "offense_team_id": 100, "defense_team_id": 200, "zone": "rim",
         "made": 0, "is_3": 0, "fgm": 0, "fg3m": 0, "assisted": 0, "fastbreak": 1},
        {"game_id": "g1", "offense_team_id": 100, "defense_team_id": 200, "zone": "corner3",
         "made": 1, "is_3": 1, "fgm": 1, "fg3m": 1, "assisted": 0, "fastbreak": 0},
        {"game_id": "g1", "offense_team_id": 100, "defense_team_id": 200, "zone": "rim",
         "made": 1, "is_3": 0, "fgm": 1, "fg3m": 0, "assisted": 0, "fastbreak": 1},
    ])
    fta = pd.DataFrame([{"game_id": "g1", "defense_team_id": 200}])  # 1 FTA allowed by defense 200

    out = aggregate_concession(shots, fta)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["defense_team_id"] == 200
    assert row["n_shots_faced"] == 4
    # overall eFG = (fgm=3 + 0.5*fg3m=1) / 4 = 0.875
    assert abs(row["overall_efg_allowed"] - 0.875) < 1e-9
    # 2 of 3 makes assisted
    assert abs(row["share_assisted_allowed"] - (1 / 3)) < 1e-9
    # 2 of 4 shots fastbreak-qualified
    assert abs(row["share_fastbreak_allowed"] - 0.5) < 1e-9
    assert abs(row["ft_rate_allowed"] - 0.25) < 1e-9
    # rim: 3 fga, 2 fgm, 0 fg3m -> efg = 2/3
    assert row["rim_fga_allowed"] == 3
    assert abs(row["rim_efg_allowed"] - (2 / 3)) < 1e-9
    assert row["corner3_fga_allowed"] == 1
    # 1 corner3 make: eFG = (fgm=1 + 0.5*fg3m=1) / 1 = 1.5 (eFG's own 3pt bonus)
    assert abs(row["corner3_efg_allowed"] - 1.5) < 1e-9


def test_zones_list_covers_five_buckets() -> None:
    assert set(ZONES) == {"rim", "paint", "mid", "corner3", "above_break_3"}


@pytest.mark.skipif(not _FIXTURE.exists(), reason="local-only data not present")
def test_load_game_shots_real_fixture() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    shots_df = load_game_shots(game_json)
    fta_df = load_game_fta(game_json)
    assert len(shots_df) > 0
    assert shots_df["zone"].isin(["rim", "paint", "mid", "corner3", "above_break_3"]).all()
    assert (shots_df["defense_team_id"] != shots_df["offense_team_id"]).all()
    out = aggregate_concession(shots_df, fta_df)
    assert len(out) == 2  # exactly 2 teams in one game
    assert (out["n_shots_faced"] > 0).all()
