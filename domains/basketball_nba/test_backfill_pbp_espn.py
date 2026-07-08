"""Per-file test for domains.basketball_nba.backfill_pbp_espn -- pure-function
coverage only (mocked ESPN payload fixture, no network, no real corpus reads).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_backfill_pbp_espn.py -q
"""
from __future__ import annotations

from domains.basketball_nba.backfill_pbp_espn import (
    _pt_clock,
    _team_map_from_summary,
    _espn_id_to_name,
    convert_game_actions,
)

_REAL_IDS = {"NYK": 1610612752, "CLE": 1610612739}
_PLAYER_MAP = {
    "karlanthony towns": 1626157,
    "guerschon yabusele": 1627824,
    "donovan mitchell": 1628378,
}


def _fixture_payload() -> dict:
    return {
        "header": {"competitions": [{
            "status": {"type": {"name": "STATUS_FINAL"}},
            "competitors": [
                {"homeAway": "home", "team": {"id": "18", "abbreviation": "NY"}},
                {"homeAway": "away", "team": {"id": "5", "abbreviation": "CLE"}},
            ],
        }]},
        "boxscore": {"players": [
            {"statistics": [{"athletes": [
                {"athlete": {"id": "3136195", "displayName": "Karl-Anthony Towns"}},
                {"athlete": {"id": "4017844", "displayName": "Guerschon Yabusele"}},
            ]}]},
            {"statistics": [{"athletes": [
                {"athlete": {"id": "3908809", "displayName": "Donovan Mitchell"}},
            ]}]},
        ]},
        "plays": [
            {
                "type": {"text": "Driving Layup Shot"},
                "text": "Donovan Mitchell makes driving layup",
                "homeScore": 5, "awayScore": 4,
                "period": {"number": 1}, "clock": {"displayValue": "10:44"},
                "team": {"id": "5"},
                "participants": [{"athlete": {"id": "3908809"}}],
                "scoringPlay": True, "shootingPlay": True, "pointsAttempted": 2,
                "coordinate": {"x": 26, "y": 1},
            },
            {
                "type": {"text": "Free Throw - 1 of 1"},
                "text": "Karl-Anthony Towns makes free throw 1 of 1",
                "homeScore": 6, "awayScore": 4,
                "period": {"number": 1}, "clock": {"displayValue": "9:00"},
                "team": {"id": "18"},
                "participants": [{"athlete": {"id": "3136195"}}],
                "scoringPlay": True, "shootingPlay": True, "pointsAttempted": 1,
                "coordinate": {"x": -214748340, "y": -214748365},
            },
            {
                "type": {"text": "Substitution"},
                "text": "Guerschon Yabusele enters the game for Karl-Anthony Towns",
                "homeScore": 12, "awayScore": 10,
                "period": {"number": 1}, "clock": {"displayValue": "7:27"},
                "team": {"id": "18"},
                "participants": [{"athlete": {"id": "4017844"}}, {"athlete": {"id": "3136195"}}],
            },
        ],
    }


def test_pt_clock_matches_liveData_regex_shape():
    assert _pt_clock(447.0) == "PT7M27.00S"
    assert _pt_clock(60.5) == "PT1M0.50S"


def test_team_map_from_summary_resolves_espn_ids_to_real_nba_ids():
    tm = _team_map_from_summary(_fixture_payload(), _REAL_IDS)
    assert tm["18"] == {"tricode": "NYK", "team_id": 1610612752}
    assert tm["5"] == {"tricode": "CLE", "team_id": 1610612739}


def test_espn_id_to_name_reads_boxscore_players():
    m = _espn_id_to_name(_fixture_payload())
    assert m[3136195] == "Karl-Anthony Towns"
    assert m[3908809] == "Donovan Mitchell"


def test_convert_game_actions_emits_shot_ft_then_sub_out_in_with_real_ids():
    actions, unmapped = convert_game_actions(_fixture_payload(), _REAL_IDS, _PLAYER_MAP)
    assert unmapped == 0
    assert [a["actionNumber"] for a in actions] == [1, 2, 3, 4]

    shot = actions[0]
    assert shot["actionType"] == "2pt" and shot["shotResult"] == "Made"
    assert shot["teamId"] == 1610612739  # CLE
    assert shot["personId"] == 1628378   # Mitchell
    # ESPN feet (x=26 width, y=1 length) -> CDN pct (x=length/94, y=width/50)
    assert abs(shot["x"] - 1.0 / 94.0 * 100.0) < 1e-9 and shot["y"] == 52.0

    ft = actions[1]
    assert ft["actionType"] == "freethrow" and ft["shotResult"] == "Made"
    assert ft["x"] is None and ft["y"] is None  # ESPN's out-of-range FT sentinel dropped

    sub_out, sub_in = actions[2], actions[3]
    assert sub_out["actionType"] == "substitution" and sub_out["subType"] == "out"
    assert sub_out["personId"] == 1626157  # Towns out
    assert sub_in["subType"] == "in"
    assert sub_in["personId"] == 1627824  # Yabusele in
    assert sub_out["teamId"] == sub_in["teamId"] == 1610612752  # NYK


def test_convert_game_actions_unmapped_name_reports_not_crashes():
    payload = _fixture_payload()
    payload["plays"][2]["text"] = "Nobody Known enters the game for Karl-Anthony Towns"
    payload["plays"][2]["participants"] = []  # force both text-regex miss paths to also miss
    actions, unmapped = convert_game_actions(payload, _REAL_IDS, _PLAYER_MAP)
    assert unmapped == 1  # 'Nobody Known' unresolved; Towns resolves fine
    subs = [a for a in actions if a["actionType"] == "substitution"]
    assert subs[0]["personId"] == 1626157  # out (Towns) still resolved
    assert subs[1]["personId"] is None      # in (unknown) honestly None, not fabricated
