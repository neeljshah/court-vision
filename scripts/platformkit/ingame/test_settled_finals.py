"""Per-file test: scripts/platformkit/ingame/test_settled_finals.py
Run: python -m pytest scripts/platformkit/ingame/test_settled_finals.py -q

Covers settled_since / _final_games_from_board for team sports (nba-shaped fixture,
existing flat-event convention) plus tennis (trimmed from a REAL ESPN tennis scoreboard
fetched live 2026-07-03, site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard,
Wimbledon). Confirmed live:
  - the `dates=` query param is IGNORED; the endpoint always returns the WHOLE tournament.
  - each top-level "event" is the TOURNAMENT itself (no top-level `competitions` key);
    real per-match competitions nest under event["groupings"][i]["competitions"].
  - competitors carry type=="athlete" + an `athlete` block (displayName), not `team`, and
    carry NO `score` field at all -- only per-set `linescores` + a `winner` bool.

NO network: settled_since is called with an injected http_get returning a canned board.
"""
from __future__ import annotations

from scripts.platformkit.ingame import settled_finals as SF


# --------------------------------------------------------------------------------------- #
# team-sport (nba) fixture -- existing flat-event shape, must stay byte-identical           #
# --------------------------------------------------------------------------------------- #
def _nba_event(*, eid="401700001", final=True, hs="110", as_="102",
               home="Boston Celtics", away="New York Knicks"):
    status_type = ({"name": "STATUS_FINAL", "state": "post", "completed": True} if final
                   else {"name": "STATUS_SCHEDULED", "state": "pre", "completed": False})
    return {
        "id": eid, "date": "2026-07-01T23:00Z",
        "competitions": [{
            "status": {"type": status_type},
            "competitors": [
                {"homeAway": "home", "score": hs, "team": {"displayName": home}},
                {"homeAway": "away", "score": as_, "team": {"displayName": away}},
            ],
        }],
    }


def test_nba_final_games_parsed_unchanged():
    board = {"events": [_nba_event()]}
    games = SF._final_games_from_board(board, "nba")
    assert len(games) == 1
    g = games[0]
    assert g["game_id"] == "401700001"
    assert g["home"] == "Boston Celtics" and g["away"] == "New York Knicks"
    assert g["home_score"] == 110.0 and g["away_score"] == 102.0


def test_nba_scheduled_game_not_final():
    board = {"events": [_nba_event(final=False)]}
    assert SF._final_games_from_board(board, "nba") == []


def test_settled_since_dedups_by_seen_ids_nba():
    board = {"events": [_nba_event(eid="A"), _nba_event(eid="B")]}
    fresh = SF.settled_since("nba", seen_ids=["A"], http_get=lambda url: board,
                             use_cache=False)
    assert [g["game_id"] for g in fresh] == ["B"]


# --------------------------------------------------------------------------------------- #
# tennis fixture -- real nested-groupings + athlete-competitor shape                        #
# --------------------------------------------------------------------------------------- #
def _tennis_match(*, match_id="179877", final=True, winner_home=True,
                  home_name="Zsombor Piros", away_name="Ivan Ivanov"):
    if final:
        status_type = {"name": "STATUS_FINAL", "state": "post", "completed": True}
        home_ls = [{"value": 6.0, "winner": winner_home}, {"value": 6.0, "winner": winner_home}]
        away_ls = [{"value": 2.0, "winner": not winner_home}, {"value": 2.0, "winner": not winner_home}]
    else:
        status_type = {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}
        home_ls = [{"value": 3.0, "winner": False}]
        away_ls = [{"value": 2.0, "winner": False}]
    return {
        "id": match_id, "date": "2026-06-22T10:05Z",
        "status": {"type": status_type},
        "competitors": [
            {"id": "13489", "type": "athlete", "homeAway": "away", "winner": not winner_home,
             "linescores": away_ls, "athlete": {"displayName": away_name}},
            {"id": "3110", "type": "athlete", "homeAway": "home", "winner": winner_home,
             "linescores": home_ls, "athlete": {"displayName": home_name}},
        ],
    }


def _tennis_board(matches):
    return {"events": [{"id": "188-2026", "name": "Wimbledon",
                        "groupings": [{"grouping": {"slug": "mens-singles"},
                                      "competitions": matches}]}]}


def test_tennis_final_match_parsed_from_nested_groupings():
    board = _tennis_board([_tennis_match()])
    games = SF._final_games_from_board(board, "tennis")
    assert len(games) == 1
    g = games[0]
    # game_id is the MATCH's own id (nested), never the tournament's ("188-2026").
    assert g["game_id"] == "179877"
    assert g["home"] == "Zsombor Piros" and g["away"] == "Ivan Ivanov"
    # sets-won fallback (tennis has no `score` field at all).
    assert g["home_score"] == 2.0 and g["away_score"] == 0.0


def test_tennis_in_progress_match_not_final():
    board = _tennis_board([_tennis_match(final=False)])
    assert SF._final_games_from_board(board, "tennis") == []


def test_tennis_multiple_nested_matches_all_surfaced():
    board = _tennis_board([
        _tennis_match(match_id="179877", home_name="Zsombor Piros", away_name="Ivan Ivanov"),
        _tennis_match(match_id="179878", home_name="Novak Djokovic", away_name="Arthur Rinderknech"),
    ])
    games = SF._final_games_from_board(board, "tennis")
    assert {g["game_id"] for g in games} == {"179877", "179878"}


def test_settled_since_tennis_dedups_by_seen_ids():
    board = _tennis_board([
        _tennis_match(match_id="179877"),
        _tennis_match(match_id="179878", home_name="Novak Djokovic",
                     away_name="Arthur Rinderknech"),
    ])
    fresh = SF.settled_since("tennis", seen_ids=["179877"],
                             http_get=lambda url: board, use_cache=False)
    assert [g["game_id"] for g in fresh] == ["179878"]


def test_tennis_never_surfaces_the_tournament_id():
    # The tournament's own id ("188-2026") must never leak in as a fake game_id.
    board = _tennis_board([_tennis_match()])
    games = SF._final_games_from_board(board, "tennis")
    assert all(g["game_id"] != "188-2026" for g in games)
