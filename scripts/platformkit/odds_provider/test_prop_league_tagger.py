"""Per-file unit tests for prop_league_tagger (NETWORK-FREE, PURE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_league_tagger.py -q

Acceptance criteria (from BACKLOG QA-PROP-LEAGUE-TAG):
  * row whose matchup/team matches a BIG3 roster/team token -> league='big3'
    (sport field is unchanged)
  * genuine NBA team in matchup/team -> league='nba'
  * unknown / novel teams -> league='unknown' (never silently 'nba')
  * pure: no network, PropLine input is NOT mutated
  * no $ field in any output
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_provider.prop_league_tagger import (
    tag_league,
    tag_rows,
    _BIG3_TEAM_TOKENS,
    _NBA_TOKENS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(
    player: str = "Test Player",
    team: str | None = None,
    match: str | None = None,
    sport: str = "nba",
) -> PropLine:
    return PropLine(
        sport=sport,
        event_id="E1",
        match=match,
        player=player,
        team=team,
        stat="Points",
        line=10.5,
        over_price=1.90,
        under_price=1.90,
        payout_type="sportsbook",
        source="underdog",
        as_of="2026-06-19T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# BIG3 team-token tests (confirmed from QA_FEED)
# ---------------------------------------------------------------------------

def test_big3_rig_hands_in_match():
    row = _make_row(match="Houston Rig Hands @ Chicago Triplets")
    assert tag_league(row) == "big3"


def test_big3_triplets_in_match():
    row = _make_row(match="Chicago Triplets vs Enemies")
    assert tag_league(row) == "big3"


def test_big3_team_in_team_field():
    row = _make_row(team="Rig Hands", match=None)
    assert tag_league(row) == "big3"


def test_big3_team_token_case_insensitive():
    row = _make_row(match="HOUSTON RIG HANDS @ CHICAGO TRIPLETS")
    assert tag_league(row) == "big3"


def test_big3_trilogy():
    row = _make_row(match="Trilogy vs Ghost Ballers")
    assert tag_league(row) == "big3"


def test_big3_ball_hogs():
    row = _make_row(team="Ball Hogs", match="Ball Hogs @ Bivouac")
    assert tag_league(row) == "big3"


def test_big3_cold_as_ice():
    row = _make_row(match="Cold As Ice vs Aliens")
    assert tag_league(row) == "big3"


def test_big3_killer_3s():
    row = _make_row(match="Killer 3s @ Trilogy")
    assert tag_league(row) == "big3"


# ---------------------------------------------------------------------------
# BIG3 player-token tests (confirmed from QA_FEED)
# ---------------------------------------------------------------------------

def test_big3_player_brandon_moss():
    row = _make_row(player="Brandon Moss", team=None, match=None)
    assert tag_league(row) == "big3"


def test_big3_player_dwight_howard():
    row = _make_row(player="Dwight Howard", team=None, match=None)
    assert tag_league(row) == "big3"


def test_big3_player_corey_brewer():
    row = _make_row(player="Corey Brewer", team=None, match=None)
    assert tag_league(row) == "big3"


def test_big3_player_case_insensitive():
    row = _make_row(player="BRANDON MOSS", team=None, match=None)
    assert tag_league(row) == "big3"


# ---------------------------------------------------------------------------
# NBA team tests
# ---------------------------------------------------------------------------

def test_nba_knicks_in_match():
    row = _make_row(match="New York Knicks vs San Antonio Spurs")
    assert tag_league(row) == "nba"


def test_nba_team_in_team_field():
    row = _make_row(team="Spurs", match="New York Knicks vs San Antonio Spurs")
    assert tag_league(row) == "nba"


def test_nba_lakers():
    row = _make_row(match="Los Angeles Lakers @ Denver Nuggets")
    assert tag_league(row) == "nba"


def test_nba_heat():
    row = _make_row(team="Heat", match="Miami Heat vs Boston Celtics")
    assert tag_league(row) == "nba"


def test_nba_warriors():
    row = _make_row(match="Golden State Warriors vs Memphis Grizzlies")
    assert tag_league(row) == "nba"


def test_nba_in_team_field_only():
    # match is None but team has NBA token
    row = _make_row(team="Bucks", match=None)
    assert tag_league(row) == "nba"


# ---------------------------------------------------------------------------
# Unknown tests -- novel teams must NEVER silently become 'nba'
# ---------------------------------------------------------------------------

def test_unknown_empty_fields():
    row = _make_row(player="John Doe", team=None, match=None)
    assert tag_league(row) == "unknown"


def test_unknown_fictional_team():
    row = _make_row(match="Fictional City Robots @ Nowhere FC", team="Robots")
    assert tag_league(row) == "unknown"


def test_unknown_generic_basketball_name():
    # A player whose name doesn't match any known token
    row = _make_row(player="Marcus Thompson", team=None, match=None)
    assert tag_league(row) == "unknown"


def test_unknown_never_silently_nba():
    # A realistic off-season exhibition matchup with no known tokens
    row = _make_row(
        player="Some ExhibitionPlayer",
        team="All-Stars",
        match="East All-Stars vs West All-Stars",
    )
    assert tag_league(row) == "unknown"


# ---------------------------------------------------------------------------
# Precedence: BIG3 beats NBA when both tokens could match
# ---------------------------------------------------------------------------

def test_big3_takes_precedence_over_nba_in_same_match():
    # A BIG3 game hosted in Houston (city token) but team token is BIG3
    row = _make_row(match="Houston Rig Hands @ Chicago Triplets")
    # 'houston' is an NBA token but 'rig hands' is BIG3 -> big3 wins
    assert tag_league(row) == "big3"


# ---------------------------------------------------------------------------
# sport field is unchanged; no $ field in output
# ---------------------------------------------------------------------------

def test_sport_field_unchanged_on_big3():
    row = _make_row(sport="nba", match="Houston Rig Hands @ Chicago Triplets")
    # sport is NOT touched by the tagger
    assert row.sport == "nba"
    assert tag_league(row) == "big3"


def test_no_dollar_field_in_tag_rows_output():
    rows = [
        _make_row(match="Houston Rig Hands @ Chicago Triplets"),
        _make_row(match="New York Knicks vs San Antonio Spurs"),
        _make_row(player="John Doe", team=None, match=None),
    ]
    result = tag_rows(rows)
    assert len(result) == 3
    for d in result:
        assert "$" not in " ".join(str(k) for k in d.keys()), \
            f"Dollar field found in output keys: {list(d.keys())}"
        assert "pnl" not in " ".join(k.lower() for k in d.keys())
        assert "roi" not in " ".join(k.lower() for k in d.keys())


# ---------------------------------------------------------------------------
# tag_rows: immutability + correct league stamps
# ---------------------------------------------------------------------------

def test_tag_rows_does_not_mutate_input():
    row = _make_row(match="Houston Rig Hands @ Chicago Triplets")
    original_sport = row.sport
    original_match = row.match
    tag_rows([row])
    assert row.sport == original_sport
    assert row.match == original_match
    # PropLine has no 'league' attribute; mutation would add one
    assert not hasattr(row, "league")


def test_tag_rows_returns_all_three_labels():
    rows = [
        _make_row(match="Houston Rig Hands @ Chicago Triplets"),
        _make_row(match="New York Knicks vs San Antonio Spurs"),
        _make_row(player="Unknown Nobody", team=None, match=None),
    ]
    result = tag_rows(rows)
    leagues = [d["league"] for d in result]
    assert "big3" in leagues
    assert "nba" in leagues
    assert "unknown" in leagues


def test_tag_rows_non_propline_skipped():
    rows = [None, "not a propline", 42, _make_row(match="Chicago Bulls vs Miami Heat")]
    result = tag_rows(rows)
    assert len(result) == 1
    assert result[0]["league"] == "nba"


def test_tag_rows_empty_input():
    assert tag_rows([]) == []


# ---------------------------------------------------------------------------
# Token set sanity checks (guard against silent removals)
# ---------------------------------------------------------------------------

def test_big3_token_set_has_confirmed_qa_tokens():
    assert "rig hands" in _BIG3_TEAM_TOKENS
    assert "triplets" in _BIG3_TEAM_TOKENS


def test_nba_token_set_has_core_franchises():
    core = {"knicks", "lakers", "celtics", "bulls", "spurs", "heat"}
    assert core.issubset(_NBA_TOKENS)
