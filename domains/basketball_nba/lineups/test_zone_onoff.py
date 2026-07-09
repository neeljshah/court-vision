"""Per-file test: defensive-side attribution (synthetic 2-team game) +
zone-split arithmetic on a hand-built stint/shot frame.

Run: python -m pytest domains/basketball_nba/lineups/test_zone_onoff.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.zone_onoff import compute_zone_onoff, load_shot_events

# Synthetic 2-team game: team 1 (101-106) on defense, team 2 (201-205) shooting.
# Team 1's lineup subs 101 -> 106 at elapsed=360s (period is 720s long).
#   shot1 (elapsed=60,  team2 rim,     made)   -> during team1's 1st stint (101 ON,  106 OFF)
#   shot2 (elapsed=100, team1's OWN shot, missed) -> must attach to team2's defense, NOT team1's
#   shot3 (elapsed=500, team2 corner3,  made)  -> during team1's 2nd stint (101 OFF, 106 ON)
_GAME_JSON = {
    "game": {
        "gameId": "0022500099",
        "actions": [
            {"actionType": "2pt", "teamId": 2, "personId": 201, "period": 1, "clock": "PT11M00S",
             "x": 5.585, "y": 50.0, "shotResult": "Made"},
            {"actionType": "2pt", "teamId": 1, "personId": 101, "period": 1, "clock": "PT10M20S",
             "x": 5.585, "y": 50.0, "shotResult": "Missed"},
            {"actionType": "3pt", "teamId": 2, "personId": 202, "period": 1, "clock": "PT3M40S",
             "x": 2.128, "y": 98.0, "shotResult": "Made"},
        ],
    }
}

_STINTS = pd.DataFrame([
    {"game_id": "0022500099", "team_id": 1, "period": 1, "lineup_key": "101,102,103,104,105",
     "n_on_court": 5, "start_s": 0.0, "end_s": 360.0, "elapsed_s": 360.0},
    {"game_id": "0022500099", "team_id": 1, "period": 1, "lineup_key": "102,103,104,105,106",
     "n_on_court": 5, "start_s": 360.0, "end_s": 720.0, "elapsed_s": 360.0},
    {"game_id": "0022500099", "team_id": 2, "period": 1, "lineup_key": "201,202,203,204,205",
     "n_on_court": 5, "start_s": 0.0, "end_s": 720.0, "elapsed_s": 720.0},
])


def test_defensive_side_attribution_synthetic_two_team_game():
    shots_df = load_shot_events(_GAME_JSON)
    # get-the-side-right sanity: every shot row is keyed on the DEFENDING
    # team, so team2's 2 makes/attempts key on team_id=1 and team1's own
    # attempt keys on team_id=2 -- never the shooter's own team.
    assert sorted(shots_df["team_id"].tolist()) == [1, 1, 2]

    shots_df = attach_lineup_to_shots(_STINTS, shots_df)
    out = compute_zone_onoff(_STINTS, shots_df).set_index("player_id")

    p101 = out.loc[101]
    assert p101["min_on"] == pytest.approx(6.0) and p101["min_off"] == pytest.approx(6.0)
    assert p101["rim_fga_on"] == 1 and p101["rim_fgm_on"] == 1
    assert p101["three_fga_on"] == 0
    assert p101["three_fga_off"] == 1 and p101["three_fgm_off"] == 1
    # only the 2 team-2 shots ever count against team 1 -- team1's own shot
    # (shot2) must not leak into its own defensive on/off split.
    assert p101["opp_fga_on"] + p101["opp_fga_off"] == 2

    p106 = out.loc[106]
    assert p106["rim_fga_off"] == 1 and p106["rim_fgm_off"] == 1
    assert p106["three_fga_on"] == 1 and p106["three_fgm_on"] == 1


def test_zone_split_math_hand_built_frame():
    stints_df = pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "1,2,3,4,5",
         "n_on_court": 5, "elapsed_s": 240.0},
        {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "2,3,4,5,6",
         "n_on_court": 5, "elapsed_s": 480.0},
    ])
    shots_df = pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "rim", "fgm": 1, "fga": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "rim", "fgm": 0, "fga": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "2,3,4,5,6", "n_on_court": 5,
         "zone": "above_break_3", "fgm": 1, "fga": 1},
    ])
    out = compute_zone_onoff(stints_df, shots_df).set_index("player_id")

    p1 = out.loc[1]  # only in the 1st stint -- on for the 2 rim shots, off for the three
    assert p1["rim_fga_on"] == 2 and p1["rim_fgm_on"] == 1
    assert p1["rim_share_allowed_on"] == pytest.approx(1.0)   # 2 rim / 2 total attempts on
    assert p1["rim_efg_allowed_on"] == pytest.approx(0.5)     # 1 make / 2 attempts
    assert p1["rim_fga_off"] == 0
    assert p1["rim_share_allowed_off"] == pytest.approx(0.0)  # denom (opp_fga_off=1) > 0, numerator 0
    assert pd.isna(p1["rim_efg_allowed_off"])                 # 0/0 -- undefined, not zero
    assert p1["three_fga_off"] == 1 and p1["three_efg_allowed_off"] == pytest.approx(1.5)

    p6 = out.loc[6]  # only in the 2nd stint -- off for the 2 rim shots, on for the three
    assert p6["rim_fga_off"] == 2 and p6["rim_fgm_off"] == 1
    assert p6["three_fga_on"] == 1 and p6["three_fgm_on"] == 1


def test_all_five_zones_split_math_hand_built_frame():
    """paint/mid/corner3/above_break_3 each get their own on/off columns,
    independent of the legacy combined 'three' bucket (which must still sum
    corner3+above_break_3, verified above) -- all 5 zone specs proven here."""
    stints_df = pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "1,2,3,4,5",
         "n_on_court": 5, "elapsed_s": 240.0},
    ])
    shots_df = pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "paint", "fgm": 1, "fga": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "mid", "fgm": 0, "fga": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "corner3", "fgm": 1, "fga": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5,
         "zone": "above_break_3", "fgm": 0, "fga": 1},
    ])
    out = compute_zone_onoff(stints_df, shots_df).set_index("player_id")
    p1 = out.loc[1]  # on-court for all 4 shots
    assert p1["paint_fga_on"] == 1 and p1["paint_fgm_on"] == 1 and p1["paint_efg_allowed_on"] == pytest.approx(1.0)
    assert p1["mid_fga_on"] == 1 and p1["mid_fgm_on"] == 0 and p1["mid_efg_allowed_on"] == pytest.approx(0.0)
    assert p1["corner3_fga_on"] == 1 and p1["corner3_efg_allowed_on"] == pytest.approx(1.5)
    assert p1["above_break_3_fga_on"] == 1 and p1["above_break_3_efg_allowed_on"] == pytest.approx(0.0)
    # legacy combined bucket still sums corner3+above_break_3 correctly
    assert p1["three_fga_on"] == 2 and p1["three_fgm_on"] == 1
    assert p1["opp_fga_on"] == 4
