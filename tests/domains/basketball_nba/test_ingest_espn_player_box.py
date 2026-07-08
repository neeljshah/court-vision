"""Per-file test for domains.basketball_nba.ingest_espn_player_box parsing.

Uses a saved (trimmed) real ESPN summary fixture -- zero network.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/domains/basketball_nba/test_ingest_espn_player_box.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from domains.basketball_nba.ingest_espn_player_box import (
    _norm_name,
    parse_summary_players,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "espn_nba_summary_trimmed.json"


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_parse_summary_players_shape_and_values():
    # Map two of the four active players to fake NBA ids; leave two unmapped.
    pmap = {_norm_name("Dean Wade"): 111, _norm_name("Miles Bridges"): 222}
    recs = parse_summary_players(_payload(), pmap)

    # 4 active athletes in the fixture; 2 DNP athletes must be skipped.
    assert len(recs) == 4
    by_name = {r["player_name"]: r for r in recs}
    assert "Thomas Bryant" not in by_name  # DNP skipped
    assert "Tidjane Salaun" not in by_name  # DNP skipped

    wade = by_name["Dean Wade"]
    # Mapped NBA id + flag; quarter_box record shape the transform consumes.
    assert wade["player_id"] == 111 and wade["player_id_mapped"] is True
    assert wade["team_abbreviation"] == "CLE"
    assert wade["min"] == "27"
    assert (wade["pts"], wade["fgm"], wade["fga"]) == (4.0, 1.0, 3.0)  # "1-3" split
    assert (wade["fg3m"], wade["fg3a"]) == (0.0, 2.0)  # "0-2" split
    assert (wade["ftm"], wade["fta"]) == (2.0, 2.0)
    assert wade["start_position"] != ""  # starter flag -> non-empty start_position

    # Unmapped player -> synthetic NEGATIVE espn id, honestly flagged.
    allen = by_name["Jarrett Allen"]
    assert allen["player_id"] == -allen["espn_player_id"] < 0
    assert allen["player_id_mapped"] is False

    # Every record carries all counting stats the transform sums.
    needed = {"pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "to",
              "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus"}
    for r in recs:
        assert needed <= set(r)


def test_norm_name_accents_and_suffixes():
    assert _norm_name("Nikola Vučević") == "nikola vucevic"
    assert _norm_name("Michael Porter Jr.") == "michael porter"
    assert _norm_name("Wendell Carter III") == "wendell carter"
