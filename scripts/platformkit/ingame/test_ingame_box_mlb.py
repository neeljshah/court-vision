"""Tests for ingame_box_mlb -- the LIVE MLB realized-stat + freshness reader.

Offline: every statsapi call is injected, so the test pins parsing/freshness/no-fabrication
without the network. The stat extraction is REUSED from prop_settler_mlb (same numbers the
post-game settler reports), so we only test the live-specific wiring here.
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_box_mlb as M


def _schedule(games):
    return {"dates": [{"games": games}]}


def _game(pk, home, away, detailed):
    return {"gamePk": pk, "status": {"detailedState": detailed, "abstractGameState":
            ("Live" if detailed == "In Progress" else "Final")},
            "teams": {"home": {"team": {"name": home}}, "away": {"team": {"name": away}}}}


def _fake_http(schedule=None, linescores=None, boxscores=None):
    schedule = schedule or {}
    linescores = linescores or {}
    boxscores = boxscores or {}

    def get(url):
        if url.startswith(M._SCHEDULE):
            return schedule
        for pk, ls in linescores.items():
            if url == M._LINESCORE % pk:
                return ls
        for pk, bx in boxscores.items():
            if url == M._BOXSCORE % pk:
                return bx
        return {}
    return get


def test_live_games_returns_only_in_progress():
    sched = _schedule([
        _game(101, "New York Mets", "Chicago Cubs", "In Progress"),
        _game(102, "Texas Rangers", "Miami Marlins", "Final"),
        _game(103, "Boston Red Sox", "New York Yankees", "Scheduled"),
    ])
    ls = {101: {"currentInning": 5, "inningState": "Top", "isTopInning": True}}
    got = M.live_games(http_get=_fake_http(schedule=sched, linescores=ls))
    assert len(got) == 1
    g = got[0]
    assert g["game_pk"] == "101" and g["home"] == "New York Mets"
    # top of the 5th -> 8 completed half-innings / 18
    assert abs(g["frac_elapsed"] - (8.0 / 18.0)) < 1e-6


def test_frac_from_linescore_endpoints():
    # top of the 1st -> nothing completed
    assert M._frac_from_linescore({"currentInning": 1, "isTopInning": True}) == 0.0
    # bottom of the 9th -> 17 of 18 halves, but capped below 1.0
    f = M._frac_from_linescore({"currentInning": 9, "isTopInning": False})
    assert 0.9 <= f <= M._FRAC_CAP
    # extra innings stays capped, never 1.0 for a live game
    assert M._frac_from_linescore({"currentInning": 12, "isTopInning": False}) <= M._FRAC_CAP
    assert M._frac_from_linescore({}) is None


def test_boxscore_stat_map_and_realized():
    box = {"teams": {
        "home": {"players": {"ID1": {"person": {"fullName": "Pete Alonso"},
                 "stats": {"batting": {"hits": 2, "rbi": 1, "totalBases": 5}}}}},
        "away": {"players": {"ID2": {"person": {"fullName": "Seiya Suzuki"},
                 "stats": {"batting": {"hits": 0, "rbi": 0}}}}},
    }}
    smap = M.boxscore_stat_map(7, http_get=_fake_http(boxscores={7: box}))
    assert M.realized_for("Hits", smap, "Pete Alonso") == 2.0
    assert M.realized_for("Total Bases", smap, "Pete Alonso") == 5.0
    assert M.realized_for("Hits", smap, "Seiya Suzuki") == 0.0


def test_realized_none_for_absent_player_not_zero():
    box = {"teams": {"home": {"players": {"ID1": {"person": {"fullName": "Pete Alonso"},
           "stats": {"batting": {"hits": 1}}}}}, "away": {"players": {}}}}
    smap = M.boxscore_stat_map(7, http_get=_fake_http(boxscores={7: box}))
    # a player with no boxscore row -> None (has not entered), NEVER a fabricated 0
    assert M.realized_for("Hits", smap, "Nobody McGhost") is None


def test_is_known_stat():
    assert M.is_known_stat("Hits") and M.is_known_stat("RBIs")
    assert M.is_known_stat("Hits+Runs+RBIs") and M.is_known_stat("Pitcher Strikeouts")
    assert not M.is_known_stat("Anytime Touchdown")
