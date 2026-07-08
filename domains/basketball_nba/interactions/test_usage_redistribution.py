"""Per-file test on the real 0022500003.json fixture: builds the tricode->
team_id map, picks top-usage players, and checks the sanity invariants --
the map recovers exactly the 2 teams in the game, top_usage_players never
returns more than TOP_N_USAGE per team, and a single 48-minute game can
never clear the 200/50-minute with/without floors (so the batch output is
empty here by construction).

Run: python -m pytest domains/basketball_nba/interactions/test_usage_redistribution.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.interactions.usage_redistribution import (
    TOP_N_USAGE,
    build_tricode_to_team_id,
    compute_usage_redistribution,
    top_usage_players,
)
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots, load_shot_events
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, build_game_stints

_FIXTURE = _PBP_DIR / "0022500003.json"


@pytest.mark.skipif(not _FIXTURE.exists() or not _BOX_SRC.exists(), reason="local-only data not present")
def test_usage_redistribution_structurally_sane_on_one_game() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    box_df = pd.read_parquet(_BOX_SRC)
    stints, notes = build_game_stints(game_json, box_df)
    assert notes == []
    stints_df = pd.DataFrame(stints)

    tricode_to_team = build_tricode_to_team_id([_FIXTURE])
    assert len(tricode_to_team) == 2

    usage_df = top_usage_players(box_df[box_df["game_id"] == game_json["game"]["gameId"]], tricode_to_team)
    assert 0 < len(usage_df) <= TOP_N_USAGE * 2
    assert (usage_df.groupby("team_id").size() <= TOP_N_USAGE).all()

    shots_df = load_shot_events(game_json)
    shots_df = attach_lineup_to_shots(stints_df, shots_df)
    result, n_excluded = compute_usage_redistribution(stints_df, shots_df, usage_df, box_df)
    # one 48-min game can never supply 200 min_with -- every candidate is excluded
    assert n_excluded == len(usage_df)
    assert len(result) == 0
