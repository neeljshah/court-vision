"""Per-file test for scripts.platformkit.ingame.kbo_naver_relay -- fixtures shaped
exactly like the real live payload captured 2026-07-04 (game 20260703HHLG02026).
No network: http_get is injected.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_naver_relay.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame.kbo_naver_relay import (
    extract_base_out_state,
    fetch_relay,
    fetch_slate,
    slate_url,
)


def _slate_fixture() -> dict:
    return {
        "code": 200,
        "success": True,
        "result": {"games": [
            {"gameId": "20260703HHLG02026", "categoryId": "kbo",
             "gameDate": "2026-07-03", "homeTeamCode": "LG", "awayTeamCode": "HH",
             "homeTeamScore": 1, "awayTeamScore": 8, "statusCode": "RESULT"},
        ]},
    }


def _relay_fixture() -> dict:
    return {
        "code": 200, "success": True,
        "result": {"textRelayData": {
            "gameId": "20260703HHLG02026",
            "currentGameState": {
                "homeScore": "1", "awayScore": "8", "homeHit": "9", "awayHit": "9",
                "homeBallFour": "1", "awayBallFour": "5", "homeError": "1",
                "awayError": "0", "pitcher": "67703", "batter": "51100",
                "strike": "3", "ball": "1", "out": "3",
                "base1": "0", "base2": "0", "base3": "4",
            },
            "inningScore": {
                "home": {"1": "0", "9": "1"},
                "away": {"1": "0", "6": "1", "8": "5", "9": "2"},
            },
            "textRelays": [{"text": "placeholder"}] * 3,
        }},
    }


def test_slate_url_builds_expected_params():
    url = slate_url("2026-07-03", "2026-07-04")
    assert url.startswith("https://api-gw.sports.naver.com/schedule/games?")
    assert "fromDate=2026-07-03" in url
    assert "toDate=2026-07-04" in url
    assert "upperCategoryId=kbaseball" in url
    assert "categoryId=kbo" in url


def test_fetch_slate_parses_games():
    games = fetch_slate("2026-07-03", "2026-07-03",
                         http_get=lambda url, timeout=15.0: _slate_fixture())
    assert len(games) == 1
    assert games[0]["gameId"] == "20260703HHLG02026"
    assert games[0]["statusCode"] == "RESULT"


def test_fetch_slate_handles_bad_shape():
    assert fetch_slate("x", "y", http_get=lambda url, timeout=15.0: {"nope": 1}) == []
    assert fetch_slate("x", "y", http_get=lambda url, timeout=15.0: (_ for _ in ()).throw(
        ConnectionError("down"))) == []


def test_fetch_relay_extracts_textrelaydata():
    trd = fetch_relay("20260703HHLG02026",
                       http_get=lambda url, timeout=15.0: _relay_fixture())
    assert trd is not None
    assert trd["currentGameState"]["homeScore"] == "1"
    assert len(trd["textRelays"]) == 3


def test_fetch_relay_none_on_missing_key():
    assert fetch_relay("x", http_get=lambda url, timeout=15.0: {"result": {}}) is None


def test_extract_base_out_state():
    trd = _relay_fixture()["result"]["textRelayData"]
    state = extract_base_out_state(trd)
    assert state == {
        "home_score": 1, "away_score": 8,
        "balls": 1, "strikes": 3, "outs": 3,
        "base1": False, "base2": False, "base3": True,
    }


def test_extract_base_out_state_none_when_missing():
    assert extract_base_out_state({}) is None
