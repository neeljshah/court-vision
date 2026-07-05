"""Per-file tests for scripts.platformkit.ingame.kbo_game_matcher.

No real network: http_get / slate_dir are injected (temp dirs, fake fetchers).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_game_matcher.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame.kbo_game_matcher import (
    naver_game_id_for,
    parse_kalshi_kbo_ticker,
    teams_for_kalshi_blob,
)

_DATE = "2026-07-05"

# Real 2026-07-05 slate shape (5 games, Naver 2-letter codes) -- see
# data/domains/kbo/slate_2026-07-05.json.
_SLATE_GAMES = [
    {"game_id": "20260705OBWO02026", "home_team": "WO", "away_team": "OB", "status": "STARTED"},
    {"game_id": "20260705HHLG02026", "home_team": "LG", "away_team": "HH", "status": "BEFORE"},
    {"game_id": "20260705LTKT02026", "home_team": "KT", "away_team": "LT", "status": "BEFORE"},
    {"game_id": "20260705NCHT02026", "home_team": "HT", "away_team": "NC", "status": "BEFORE"},
    {"game_id": "20260705SSSK02026", "home_team": "SK", "away_team": "SS", "status": "BEFORE"},
]


def _write_cache(tmp_path: Path, games=None) -> Path:
    slate_dir = tmp_path / "kbo"
    slate_dir.mkdir(parents=True, exist_ok=True)
    payload = {"date_kst": _DATE, "games_found": len(games or _SLATE_GAMES),
               "games": games if games is not None else _SLATE_GAMES}
    (slate_dir / ("slate_%s.json" % _DATE)).write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return slate_dir


def test_matches_from_cached_slate_home_kt_away_lotte(tmp_path):
    slate_dir = _write_cache(tmp_path)
    gid = naver_game_id_for(_DATE, "KT", "LOTTE", slate_dir=slate_dir)
    assert gid == "20260705LTKT02026"


def test_matches_from_cached_slate_kiwoom_vs_doosan(tmp_path):
    slate_dir = _write_cache(tmp_path)
    gid = naver_game_id_for(_DATE, "KIWOOM", "DOOSAN", slate_dir=slate_dir)
    assert gid == "20260705OBWO02026"


def test_all_five_cached_games_resolve(tmp_path):
    slate_dir = _write_cache(tmp_path)
    pairs = [("KT", "LOTTE"), ("LG", "HANWHA"), ("KIA", "NC"), ("SSG", "SAMSUNG"),
             ("KIWOOM", "DOOSAN")]
    resolved = {naver_game_id_for(_DATE, h, a, slate_dir=slate_dir) for h, a in pairs}
    assert resolved == {g["game_id"] for g in _SLATE_GAMES}


def test_swapped_home_away_does_not_match(tmp_path):
    slate_dir = _write_cache(tmp_path)
    # Real matchup is home=KT away=LOTTE; the reverse must NOT resolve (never fuzzy/swap).
    assert naver_game_id_for(_DATE, "LOTTE", "KT", slate_dir=slate_dir) is None


def test_unmapped_en_code_returns_none_without_fetch(tmp_path):
    slate_dir = tmp_path / "kbo"  # no cache file, no http_get -- must not attempt network
    assert naver_game_id_for(_DATE, "NOTATEAM", "LOTTE", slate_dir=slate_dir) is None


def test_no_matching_game_in_slate_returns_none(tmp_path):
    slate_dir = _write_cache(tmp_path)
    # KT vs KIA never plays itself; KT already plays LOTTE that day.
    assert naver_game_id_for(_DATE, "KT", "KIA", slate_dir=slate_dir) is None


def test_stale_cache_wrong_date_triggers_refetch(tmp_path):
    slate_dir = tmp_path / "kbo"
    slate_dir.mkdir(parents=True, exist_ok=True)
    # Cache file exists but its OWN date_kst is a different day -- must be ignored.
    stale = {"date_kst": "2026-07-04", "games_found": 1,
             "games": [{"game_id": "WRONG", "home_team": "KT", "away_team": "LT"}]}
    (slate_dir / ("slate_%s.json" % _DATE)).write_text(
        json.dumps(stale, ensure_ascii=True), encoding="utf-8")

    def fake_http_get(url, timeout=15.0):
        return {"result": {"games": [
            {"gameId": "FRESHID", "homeTeamCode": "KT", "awayTeamCode": "LT",
             "statusCode": "BEFORE"},
        ]}}

    gid = naver_game_id_for(_DATE, "KT", "LOTTE", slate_dir=slate_dir, http_get=fake_http_get)
    assert gid == "FRESHID"


def test_empty_slate_and_dead_fetch_returns_none_never_raises(tmp_path):
    slate_dir = tmp_path / "kbo"

    def boom(url, timeout=15.0):
        raise ConnectionError("down")

    assert naver_game_id_for(_DATE, "KT", "LOTTE", slate_dir=slate_dir,
                             http_get=boom) is None


def test_refetch_writes_cache_for_next_call(tmp_path):
    slate_dir = tmp_path / "kbo"
    calls = {"n": 0}

    def fake_http_get(url, timeout=15.0):
        calls["n"] += 1
        return {"result": {"games": [
            {"gameId": "ONLYCALL", "homeTeamCode": "KT", "awayTeamCode": "LT",
             "statusCode": "BEFORE"},
        ]}}

    gid1 = naver_game_id_for(_DATE, "KT", "LOTTE", slate_dir=slate_dir, http_get=fake_http_get)
    assert gid1 == "ONLYCALL"
    assert calls["n"] == 1
    # Second call should read the just-written cache, NOT refetch.
    gid2 = naver_game_id_for(_DATE, "KT", "LOTTE", slate_dir=slate_dir, http_get=fake_http_get)
    assert gid2 == "ONLYCALL"
    assert calls["n"] == 1


def test_parse_kalshi_kbo_ticker_valid():
    parsed = parse_kalshi_kbo_ticker("KXKBOGAME-26JUL070530NCDHAN")
    assert parsed == {"yy": "26", "mon": "JUL", "dd": "07", "hhmm": "0530", "blob": "NCDHAN"}


def test_parse_kalshi_kbo_ticker_rejects_non_kbo():
    assert parse_kalshi_kbo_ticker("KXMLBGAME-26JUN271810AZTB") is None
    assert parse_kalshi_kbo_ticker("garbage") is None
    assert parse_kalshi_kbo_ticker(None) is None


def test_teams_for_kalshi_blob_real_cases():
    # Every ticker cached live 2026-07-04/05 (see kbo_team_alias's docstring).
    cases = {
        "NCDHAN": {"NC", "HANWHA"}, "KIWKTW": {"KIWOOM", "KT"}, "LGSAM": {"LG", "SAMSUNG"},
        "KIALOT": {"KIA", "LOTTE"}, "SSGDOO": {"SSG", "DOOSAN"}, "NCDKIA": {"NC", "KIA"},
        "LOTKTW": {"LOTTE", "KT"}, "SAMSSG": {"SAMSUNG", "SSG"}, "HANLG": {"HANWHA", "LG"},
        "DOOKIW": {"DOOSAN", "KIWOOM"},
    }
    for blob, expected in cases.items():
        pair = teams_for_kalshi_blob(blob)
        assert pair is not None, blob
        assert set(pair) == expected, blob


def test_teams_for_kalshi_blob_unknown_returns_none():
    assert teams_for_kalshi_blob("ZZZZZZ") is None
    assert teams_for_kalshi_blob("") is None
    assert teams_for_kalshi_blob(None) is None


def test_full_ticker_to_naver_gameid_chain(tmp_path):
    """END-TO-END: real Kalshi ticker -> alias -> matcher -> Naver gameId, no network.

    Ticker cached live 2026-07-04 (KT vs LOTTE); resolved against the 2026-07-05 slate
    fixture, which models the SAME KT/LOTTE matchup on a different calendar day."""
    slate_dir = _write_cache(tmp_path)
    parsed = parse_kalshi_kbo_ticker("KXKBOGAME-26JUL050500LOTKTW")
    assert parsed is not None
    pair = teams_for_kalshi_blob(parsed["blob"])
    assert pair is not None
    en1, en2 = pair
    # Try both orders since the pair is unordered; exactly one order matches the slate.
    gid = naver_game_id_for(_DATE, en1, en2, slate_dir=slate_dir) or \
        naver_game_id_for(_DATE, en2, en1, slate_dir=slate_dir)
    assert gid == "20260705LTKT02026"
