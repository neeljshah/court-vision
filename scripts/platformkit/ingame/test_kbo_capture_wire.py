"""Per-file tests for scripts.platformkit.ingame.kbo_capture_wire.

No real network: slate_dir/http_get/relay_http_get are all injected. The relay fixture
is the ACTUAL LIVE payload from data/domains/kbo/naver_relay_live_sample_2026-07-05.json
(same fixture test_kbo_relay_state_provider.py uses).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_capture_wire.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame.kbo_capture_wire import (
    kbo_deep_state_for_ticker,
    make_kbo_deep_fn,
)

_DATE = "2026-07-05"
_GID = "20260705OBWO02026"

# Real slate row for the OB/WO matinee (kiwoom home, doosan away) -- see
# data/domains/kbo/slate_2026-07-05.json.
_SLATE_GAMES = [
    {"game_id": _GID, "home_team": "WO", "away_team": "OB", "status": "STARTED"},
]

# REAL live relay payload, poll 1 of 2 (as_of 2026-07-05T07:29:05Z) -- see
# data/domains/kbo/naver_relay_live_sample_2026-07-05.json.
_RELAY_FIXTURE = {
    "category": "kbo", "gameId": _GID, "no": 79, "inn": 8, "homeOrAway": "0",
    "currentGameState": {
        "homeScore": "1", "awayScore": "5", "homeHit": "6", "awayHit": "8",
        "homeBallFour": "1", "awayBallFour": "3", "homeError": "1", "awayError": "0",
        "pitcher": "76118", "batter": "53554",
        "strike": "0", "ball": "1", "out": "2",
        "base1": "0", "base2": "8", "base3": "0",
    },
    "inningScore": {
        "home": {"1": "0", "2": "0", "3": "1", "4": "0", "5": "0", "6": "0", "7": "0", "8": "-"},
        "away": {"1": "0", "2": "1", "3": "0", "4": "3", "5": "0", "6": "0", "7": "0", "8": "1"},
    },
}

# Real observed ticker: the OB/WO matinee's Kalshi blob is KIW(Kiwoom=home)+DOO(Doosan=away)
# -- reusing the DOOKIW blob verified live 2026-07-04 in kbo_team_alias's docstring, on a
# ticker shaped for today's date so the end-to-end chain resolves against _SLATE_GAMES.
_TICKER = "KXKBOGAME-26JUL050100DOOKIW"


def _write_slate_cache(tmp_path: Path) -> Path:
    slate_dir = tmp_path / "kbo"
    slate_dir.mkdir(parents=True, exist_ok=True)
    payload = {"date_kst": _DATE, "games_found": len(_SLATE_GAMES), "games": _SLATE_GAMES}
    (slate_dir / ("slate_%s.json" % _DATE)).write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return slate_dir


def _relay_http_get(url, timeout=15.0):
    return {"result": {"textRelayData": _RELAY_FIXTURE}}


def test_happy_path_resolves_a_real_state_row(tmp_path):
    """(i) happy path: a real Kalshi ticker resolves through alias->matcher->relay to a
    genuine as-of state row (not an empty dict)."""
    slate_dir = _write_slate_cache(tmp_path)
    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=slate_dir, relay_http_get=_relay_http_get)
    assert row != {}
    assert row["game_id"] == _GID
    assert row["inning"] == 8
    assert row["half"] == "top"
    assert row["outs"] == 2
    assert row["score_home"] == 1
    assert row["score_away"] == 5


def test_make_kbo_deep_fn_closure_matches_direct_call(tmp_path):
    slate_dir = _write_slate_cache(tmp_path)
    deep_fn = make_kbo_deep_fn(date=_DATE, slate_dir=slate_dir, relay_http_get=_relay_http_get)
    row = deep_fn(_TICKER)
    assert row["game_id"] == _GID
    assert row["score_away"] == 5


def test_non_kbo_ticker_returns_empty_dict_not_none(tmp_path):
    slate_dir = _write_slate_cache(tmp_path)
    row = kbo_deep_state_for_ticker(
        "KXMLBGAME-26JUN271810AZTB", date=_DATE, slate_dir=slate_dir,
        relay_http_get=_relay_http_get)
    assert row == {}


def test_unresolvable_blob_returns_empty_dict(tmp_path):
    slate_dir = _write_slate_cache(tmp_path)
    row = kbo_deep_state_for_ticker(
        "KXKBOGAME-26JUL050100ZZZZZZ", date=_DATE, slate_dir=slate_dir,
        relay_http_get=_relay_http_get)
    assert row == {}


def test_slate_miss_returns_empty_dict(tmp_path):
    """A ticker whose teams are real but never play each other on this date -> {}.

    An empty cached slate (games: []) is treated as absent (kbo_game_matcher's
    _slate_games re-fetches on an empty list) -- so http_get is injected to return a
    non-matching live slate rather than relying on a stale/empty cache short-circuiting
    (that would also correctly fall through to a real network call in production, which
    is out of scope for an offline test)."""
    empty_slate = tmp_path / "kbo"

    def no_match_http_get(url, timeout=15.0):
        return {"result": {"games": [
            {"gameId": "OTHERGAME", "homeTeamCode": "LG", "awayTeamCode": "HH",
             "statusCode": "BEFORE"},
        ]}}

    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=empty_slate, http_get=no_match_http_get,
        relay_http_get=_relay_http_get)
    assert row == {}


def test_injected_exception_at_matcher_hop_returns_empty_dict_never_raises(tmp_path):
    """(ii) injected exception (slate http_get) leaves the base path untouched: the
    wire degrades to {} instead of propagating, exactly like a dead MLB resolver."""
    slate_dir = tmp_path / "kbo"  # no cache file -> matcher must attempt a fetch

    def boom(url, timeout=15.0):
        raise ConnectionError("down")

    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=slate_dir, http_get=boom,
        relay_http_get=_relay_http_get)
    assert row == {}


def test_injected_exception_at_relay_hop_returns_empty_dict_never_raises(tmp_path):
    """(ii) relay fetch throws -> wire still degrades to {}, never raises."""
    slate_dir = _write_slate_cache(tmp_path)

    def boom(url, timeout=15.0):
        raise ConnectionError("relay down")

    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=slate_dir, relay_http_get=boom)
    assert row == {}


def test_malformed_ticker_never_raises():
    assert kbo_deep_state_for_ticker(None) == {}
    assert kbo_deep_state_for_ticker("garbage") == {}
    assert kbo_deep_state_for_ticker("") == {}


def test_happy_path_appends_state_row_to_disk(tmp_path):
    """BUGFIX regression (kbo-runtime-verify lane, wave-56): a successful resolve must
    also persist via kbo_relay_state_provider.append_state_row -- previously this wire
    called relay_state_for_game directly and never appended, so data/cache/
    kbo_relay_state/ silently never gained rows through this path even on a fully
    healthy chain. capture=True (the production default) must write a real .jsonl."""
    slate_dir = _write_slate_cache(tmp_path)
    out_dir = tmp_path / "kbo_relay_state"
    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=slate_dir, relay_http_get=_relay_http_get,
        out_dir=out_dir)
    assert row != {}
    state_file = out_dir / ("%s.jsonl" % _GID)
    assert state_file.is_file()
    lines = state_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["game_id"] == _GID
    assert written["inning"] == 8


def test_capture_false_never_writes_to_disk(tmp_path):
    """capture=False (pure-lookup mode) must resolve the row but never touch disk."""
    slate_dir = _write_slate_cache(tmp_path)
    out_dir = tmp_path / "kbo_relay_state"
    row = kbo_deep_state_for_ticker(
        _TICKER, date=_DATE, slate_dir=slate_dir, relay_http_get=_relay_http_get,
        capture=False, out_dir=out_dir)
    assert row != {}
    assert not out_dir.exists()
