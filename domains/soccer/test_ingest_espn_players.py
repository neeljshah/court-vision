"""Per-file test for domains.soccer.ingest_espn_players (network-free).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_ingest_espn_players.py -q
"""
from __future__ import annotations

from domains.soccer.ingest_espn_players import (
    _derive_minutes,
    _parse_minute,
    _parse_player_summary,
)


def _stats(**kw):
    """Build an ESPN stats list from name=value kwargs (value numeric)."""
    return [{"name": n, "value": v, "displayValue": str(v)} for n, v in kw.items()]


def _canned_payload():
    """2 teams; players: a starter who played full, a starter subbed OFF at 70',
    a sub who came ON at 70', an unused sub (no stats), and a GK."""
    return {
        "keyEvents": [
            {
                "type": {"text": "Substitution", "type": "substitution"},
                "clock": {"displayValue": "70'"},
                "participants": [
                    {"athlete": {"id": "101"}},  # came on
                    {"athlete": {"id": "100"}},  # came off
                ],
            }
        ],
        "rosters": [
            {
                "homeAway": "home",
                "team": {"abbreviation": "FRA"},
                "roster": [
                    {  # starter, played full 90
                        "athlete": {"id": "99", "displayName": "Mbappe"},
                        "position": {"abbreviation": "F"},
                        "starter": True, "subbedIn": False, "subbedOut": False,
                        "stats": _stats(totalShots=5, shotsOnTarget=3, foulsCommitted=1,
                                        goalAssists=0, totalGoals=2),
                    },
                    {  # starter subbed OFF at 70'
                        "athlete": {"id": "100", "displayName": "Griezmann"},
                        "position": {"abbreviation": "M"},
                        "starter": True, "subbedIn": False, "subbedOut": True,
                        "stats": _stats(totalShots=2, shotsOnTarget=1, foulsCommitted=2),
                    },
                    {  # sub came ON at 70'
                        "athlete": {"id": "101", "displayName": "Cherki"},
                        "position": {"abbreviation": "M"},
                        "starter": False, "subbedIn": True, "subbedOut": False,
                        "stats": _stats(totalShots=1, shotsOnTarget=0),
                    },
                    {  # GK
                        "athlete": {"id": "98", "displayName": "Maignan"},
                        "position": {"abbreviation": "G"},
                        "starter": True, "subbedIn": False, "subbedOut": False,
                        "stats": _stats(saves=4, foulsCommitted=0),
                    },
                ],
            },
            {
                "homeAway": "away",
                "team": {"abbreviation": "SEN"},
                "roster": [
                    {  # unused sub: never played, no stats
                        "athlete": {"id": "200", "displayName": "Unused Sub"},
                        "position": {"abbreviation": "D"},
                        "starter": False, "subbedIn": False, "subbedOut": False,
                        "stats": [],
                    },
                ],
            },
        ],
    }


def _by_id(rows):
    return {r["player_id"]: r for r in rows}


def test_parse_minute():
    assert _parse_minute("70'") == 70
    assert _parse_minute("90+3") == 90
    assert _parse_minute(None) is None
    assert _parse_minute("") is None


def test_derive_minutes_branches():
    assert _derive_minutes(True, False, False, None) == (90.0, False)   # full starter
    assert _derive_minutes(True, False, True, 70) == (70.0, False)      # subbed off
    assert _derive_minutes(False, True, False, 70) == (20.0, False)     # subbed on (90-70)
    assert _derive_minutes(False, False, False, None) == (0.0, False)   # never played
    # missing minute -> fallback + estimated flag
    assert _derive_minutes(True, False, True, None) == (90.0, True)
    assert _derive_minutes(False, True, False, None)[1] is True


def test_row_count_and_flags():
    rows = _parse_player_summary(_canned_payload(), "EVT1", "fifa.world")
    assert len(rows) == 5  # unused sub is KEPT
    rmap = _by_id(rows)
    assert set(rmap) == {"99", "100", "101", "98", "200"}
    assert rmap["99"]["starter"] is True and rmap["99"]["subbed_out"] is False
    assert rmap["100"]["subbed_out"] is True
    assert rmap["101"]["subbed_in"] is True and rmap["101"]["starter"] is False
    assert rmap["200"]["starter"] is False and rmap["200"]["subbed_in"] is False
    assert rmap["99"]["team_abbr"] == "FRA" and rmap["99"]["home_away"] == "home"
    assert rmap["200"]["team_abbr"] == "SEN" and rmap["200"]["home_away"] == "away"


def test_stats_parsed_to_numbers():
    rmap = _by_id(_parse_player_summary(_canned_payload(), "EVT1", "fifa.world"))
    assert rmap["99"]["totalShots"] == 5.0
    assert rmap["99"]["shotsOnTarget"] == 3.0
    assert rmap["99"]["totalGoals"] == 2.0
    assert rmap["98"]["saves"] == 4.0          # GK stat
    assert rmap["200"]["totalShots"] is None   # unused sub: stat None, not dropped


def test_minutes_derived_correctly():
    rmap = _by_id(_parse_player_summary(_canned_payload(), "EVT1", "fifa.world"))
    assert rmap["99"]["minutes"] == 90.0       # starter full
    assert rmap["100"]["minutes"] == 70.0      # subbed off at 70'
    assert rmap["101"]["minutes"] == 20.0      # subbed on at 70' -> 90-70
    assert rmap["200"]["minutes"] == 0.0       # unused sub
    assert rmap["99"]["minutes_estimated"] is False


def test_empty_payload_degrades():
    assert _parse_player_summary({}, "X", "fifa.world") == []
    assert _parse_player_summary({"rosters": None}, "X", "fifa.world") == []
