"""Network-free tests for domains.mlb.ingest_player_stats._parse_boxscore.

Canned boxscore: one batter (hits/TB/RBI) + one pitcher (outs/K/ER). Asserts the
is_pitcher flag, that the pitcher's strikeOuts is stored separately from the
batter's, and that numbers parse. Run per-file (NEVER full pytest):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingest_player_stats.py -q
"""
from domains.mlb.ingest_player_stats import (
    _innings_to_float,
    _parse_boxscore,
    fetch_finals_for_date,
    fetch_game,
)

_BOX = {
    "teams": {
        "home": {
            "team": {"id": 143, "name": "Philadelphia Phillies", "abbreviation": "PHI"},
            "players": {
                "ID669016": {
                    "person": {"id": 669016, "fullName": "Brandon Marsh"},
                    "position": {"abbreviation": "LF"},
                    "battingOrder": "100",
                    "stats": {
                        "batting": {
                            "atBats": 3, "hits": 1, "totalBases": 4, "rbi": 2,
                            "runs": 2, "homeRuns": 1, "doubles": 0, "triples": 0,
                            "baseOnBalls": 1, "strikeOuts": 1, "stolenBases": 1,
                            "hitByPitch": 0,
                        },
                        "pitching": {},
                    },
                },
                "ID666200": {
                    "person": {"id": 666200, "fullName": "Jesus Luzardo"},
                    "position": {"abbreviation": "P"},
                    "battingOrder": None,
                    "stats": {
                        "batting": {},
                        "pitching": {
                            "outs": 21, "inningsPitched": "7.0", "strikeOuts": 9,
                            "earnedRuns": 2, "hits": 5, "baseOnBalls": 2,
                            "battersFaced": 28,
                        },
                    },
                },
            },
        },
        "away": {
            "team": {"id": 146, "name": "Miami Marlins", "abbreviation": "MIA"},
            "players": {},
        },
    }
}


def _rows():
    return {r["player_id"]: r for r in _parse_boxscore(_BOX, 823451, "2026-06-16")}


def test_two_rows_one_per_player():
    rows = _parse_boxscore(_BOX, 823451, "2026-06-16")
    assert len(rows) == 2
    for r in rows:
        assert r["game_pk"] == 823451
        assert r["date"] == "2026-06-16"
        assert r["team"] == "PHI"


def test_batter_parsed():
    b = _rows()[669016]
    assert b["is_pitcher"] is False
    assert b["player"] == "Brandon Marsh"
    assert b["position"] == "LF"
    assert b["batting_order"] == 1
    assert b["hits"] == 1.0
    assert b["totalBases"] == 4.0
    assert b["rbi"] == 2.0
    assert b["homeRuns"] == 1.0
    assert b["strikeOuts"] == 1.0  # batter K
    # position player has no pitching -> pitching cols None
    assert b["pitch_strikeOuts"] is None
    assert b["earnedRuns"] is None
    assert b["inningsPitched"] is None


def test_pitcher_parsed_and_k_separate():
    p = _rows()[666200]
    assert p["is_pitcher"] is True
    assert p["position"] == "P"
    assert p["batting_order"] is None
    assert p["outs"] == 21.0
    assert p["earnedRuns"] == 2.0
    assert p["battersFaced"] == 28.0
    assert p["inningsPitched"] == 7.0
    # pitcher K stored separately from batter K column
    assert p["pitch_strikeOuts"] == 9.0
    assert p["strikeOuts"] is None  # no batting -> batter K col is None
    assert p["hits_allowed"] == 5.0
    assert p["baseOnBalls_allowed"] == 2.0


def test_innings_fractional():
    assert _innings_to_float("7.0") == 7.0
    assert abs(_innings_to_float("6.2") - (6 + 2.0 / 3.0)) < 1e-9
    assert abs(_innings_to_float("5.1") - (5 + 1.0 / 3.0)) < 1e-9
    assert _innings_to_float(None) is None


def test_empty_payload_degrades():
    assert _parse_boxscore({}, 1, "2026-06-16") == []
    assert _parse_boxscore(None, 1, "2026-06-16") == []
    assert _parse_boxscore({"teams": "bad"}, 1, "2026-06-16") == []


def test_fetch_helpers_with_injected_http_get():
    sched = {"dates": [{"games": [
        {"gamePk": 111, "status": {"abstractGameState": "Final"}},
        {"gamePk": 222, "status": {"abstractGameState": "Live"}},
    ]}]}
    assert fetch_finals_for_date("2026-06-16", http_get=lambda u: sched) == [111]
    rows = fetch_game(823451, http_get=lambda u: _BOX)
    assert len(rows) == 2
