"""Per-file test for prop_settler_mlb -- resolve the realized MLB stat from a (canned)
keyless statsapi boxscore. No network: http_get is injected.

Run ONLY this file:
    python -m pytest scripts/platformkit/bestbets/test_prop_settler_mlb.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import prop_settler_mlb as M

_GAMEPK = "777001"


def _schedule(state="Final"):
    return {"dates": [{"games": [{
        "gamePk": _GAMEPK,
        "status": {"abstractGameState": state, "detailedState": state},
        "teams": {"home": {"team": {"name": "Boston Red Sox"}},
                  "away": {"team": {"name": "New York Yankees"}}},
    }]}]}


def _boxscore():
    return {"teams": {"away": {"players": {
        "ID592450": {"person": {"fullName": "Aaron Judge"},
                     "stats": {"batting": {"hits": 2, "totalBases": 5, "rbi": 3,
                                           "runs": 1, "homeRuns": 1, "strikeOuts": 1}}},
        "ID605483": {"person": {"fullName": "Gerrit Cole"},
                     "stats": {"pitching": {"strikeOuts": 8, "outs": 18}}},
    }}, "home": {"players": {}}}}


def _http_factory(schedule, box):
    def _get(url):
        return box if "boxscore" in url else schedule
    return _get


def _row(player="Aaron Judge", stat="Hits"):
    return {"sport": "mlb", "matchup": "New York Yankees @ Boston Red Sox",
            "prop_player": player, "prop_stat": stat, "line": 1.5, "side": "home",
            "prop_side": "over", "game_date": "2026-06-21"}


def test_batting_stats_resolve():
    get = _http_factory(_schedule(), _boxscore())
    assert M.mlb_realized_stat(_row(stat="Hits"), http_get=get) == 2.0
    assert M.mlb_realized_stat(_row(stat="Total Bases"), http_get=get) == 5.0
    assert M.mlb_realized_stat(_row(stat="RBIs"), http_get=get) == 3.0
    assert M.mlb_realized_stat(_row(stat="Home Runs"), http_get=get) == 1.0


def test_hits_runs_rbis_composite():
    get = _http_factory(_schedule(), _boxscore())
    # 2 hits + 1 run + 3 rbi = 6
    assert M.mlb_realized_stat(_row(stat="Hits+Runs+RBIs"), http_get=get) == 6.0


def test_pitcher_stats_resolve():
    get = _http_factory(_schedule(), _boxscore())
    assert M.mlb_realized_stat(_row(player="Gerrit Cole", stat="Pitcher Strikeouts"),
                               http_get=get) == 8.0
    assert M.mlb_realized_stat(_row(player="Gerrit Cole", stat="Outs"),
                               http_get=get) == 18.0


def test_not_final_returns_none():
    get = _http_factory(_schedule(state="In Progress"), _boxscore())
    assert M.mlb_realized_stat(_row(), http_get=get) is None


def test_player_not_in_boxscore_returns_none_not_zero():
    get = _http_factory(_schedule(), _boxscore())
    # DNP / wrong player -> None (PENDING), never a fabricated 0
    assert M.mlb_realized_stat(_row(player="Nobody Here", stat="Hits"), http_get=get) is None


def test_unknown_stat_returns_none():
    get = _http_factory(_schedule(), _boxscore())
    assert M.mlb_realized_stat(_row(stat="Triples Galore"), http_get=get) is None


def test_empty_feed_is_safe():
    assert M.mlb_realized_stat(_row(), http_get=lambda u: {}) is None
