"""Per-file test (spec: real single-game fixture, no mocks). Loads the real
0022500003.json PBP file (verified clean, zero quality notes) + the real
box-score parquet and asserts the two invariants the module docstring
promises: every stint has exactly 5 on-court players, and each team's total
stint seconds equal the 4-quarter game length (2880s), within tolerance.

Run: python -m pytest domains/basketball_nba/lineups/test_pbp_lineups.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.lineups.pbp_lineups import REPO_ROOT, _BOX_SRC, _PBP_DIR, build_game_stints

_FIXTURE = _PBP_DIR / "0022500003.json"


@pytest.mark.skipif(not _FIXTURE.exists() or not _BOX_SRC.exists(), reason="local-only data not present")
def test_clean_game_every_stint_has_five_players_and_full_game_length() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    box_df = pd.read_parquet(_BOX_SRC)

    stints, notes = build_game_stints(game_json, box_df)
    assert notes == [], f"expected zero quality notes on this known-clean fixture, got: {notes}"
    assert len(stints) > 0

    df = pd.DataFrame(stints)
    assert (df["n_on_court"] == 5).all(), "every stint must have exactly 5 on-court players"

    per_team = df.groupby("team_id")["elapsed_s"].sum()
    assert len(per_team) == 2
    for team_id, total_s in per_team.items():
        assert abs(total_s - 2880.0) < 1e-6, f"team {team_id} total stint seconds {total_s} != 2880 (4x12min)"

    # face validity: known starters actually appear as the seed lineup_key members
    first_stint = df[df["period"] == 1].iloc[0]
    assert first_stint["lineup_key"].count(",") == 4  # 5 personIds joined by 4 commas
