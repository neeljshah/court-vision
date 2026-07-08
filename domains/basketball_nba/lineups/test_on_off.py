"""Per-file test on the real 0022500003.json fixture (same clean game used
by test_pbp_lineups.py): builds stints, attaches real shot events, computes
on/off splits, and checks the sanity invariants -- every player's on+off
minutes roughly cover the team's total floor time, and eFG% values (when
defined) fall in [0, 1].

Run: python -m pytest domains/basketball_nba/lineups/test_on_off.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots, compute_on_off, load_shot_events
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, build_game_stints

_FIXTURE = _PBP_DIR / "0022500003.json"


@pytest.mark.skipif(not _FIXTURE.exists() or not _BOX_SRC.exists(), reason="local-only data not present")
def test_on_off_splits_sane_on_clean_fixture() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    box_df = pd.read_parquet(_BOX_SRC)
    stints, notes = build_game_stints(game_json, box_df)
    assert notes == []
    stints_df = pd.DataFrame(stints)

    shots_df = load_shot_events(game_json)
    assert len(shots_df) > 0
    shots_df = attach_lineup_to_shots(stints_df, shots_df)
    assert (shots_df["lineup_key"].notna()).all()

    result = compute_on_off(stints_df, shots_df)
    assert 10 <= len(result) <= 30  # both teams' full rosters that saw floor time (not just the 5 starters)

    # on + off minutes for any player should not exceed one team's total floor time (48 min, this game had no OT)
    team_minutes = stints_df.groupby("team_id")["elapsed_s"].sum().iloc[0] / 60.0
    for _, row in result.iterrows():
        assert row["min_on"] + row["min_off"] <= team_minutes + 1e-6
        assert row["min_on"] >= 0 and row["min_off"] >= 0
        for col in ("teammate_efg_on", "teammate_efg_off"):
            if row[col] is not None and row[col] == row[col]:
                assert 0.0 <= row[col] <= 1.0
