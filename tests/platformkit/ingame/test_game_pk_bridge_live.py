"""Tests for scripts.platformkit.ingame.game_pk_bridge_live.

All network calls are faked via an injected http callable -- no live traffic in
the per-file test run. Covers: happy-path 3-way resolution, unresolvable team
name -> None (never guessed), ambiguous ESPN doubleheader key -> None for every
game sharing it, and a Kalshi ticker for a DIFFERENT date never mismatching in.
"""
from __future__ import annotations

from scripts.platformkit.ingame.game_pk_bridge_live import (
    BridgeRow, build_bridge, summarize,
)


def _schedule_body(games):
    return {"dates": [{"games": [
        {"gamePk": g["game_pk"],
         "teams": {"away": {"team": {"name": g["away"]}},
                   "home": {"team": {"name": g["home"]}}}}
        for g in games
    ]}]}


def _espn_body(events):
    out = []
    for i, (away, home) in enumerate(events):
        out.append({
            "id": str(1000 + i),
            "competitions": [{"competitors": [
                {"homeAway": "away", "team": {"displayName": away}},
                {"homeAway": "home", "team": {"displayName": home}},
            ]}],
        })
    return {"events": out}


def _kalshi_body(tickers):
    return {"markets": [{"ticker": t, "event_ticker": t} for t in tickers]}


def _fake_http(schedule, espn, kalshi):
    def http(url: str):
        if "statsapi.mlb.com" in url:
            return schedule
        if "site.api.espn.com" in url:
            return espn
        if "kalshi.com" in url:
            return kalshi
        return None
    return http


def test_happy_path_resolves_all_three():
    games = [{"game_pk": 111, "away": "St. Louis Cardinals", "home": "Chicago Cubs"}]
    schedule = _schedule_body(games)
    espn = _espn_body([("St. Louis Cardinals", "Chicago Cubs")])
    kalshi = _kalshi_body(["KXMLBGAME-26JUL031805STLCHC"])
    http = _fake_http(schedule, espn, kalshi)

    rows = build_bridge("2026-07-03", http=http)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, BridgeRow)
    assert r.game_pk == 111
    assert r.espn_id == "1000"
    assert r.kalshi_ticker_stem == "KXMLBGAME-26JUL031805STLCHC"

    summary = summarize(rows)
    assert summary["n_bridged_all_three"] == 1
    assert summary["n_games"] == 1


def test_unresolvable_team_name_never_guesses():
    games = [{"game_pk": 222, "away": "Some Exhibition XYZ", "home": "Chicago Cubs"}]
    schedule = _schedule_body(games)
    espn = _espn_body([("Some Exhibition XYZ", "Chicago Cubs")])
    kalshi = _kalshi_body([])
    http = _fake_http(schedule, espn, kalshi)

    rows = build_bridge("2026-07-03", http=http)
    assert len(rows) == 1
    assert rows[0].espn_id is None
    assert rows[0].kalshi_ticker_stem is None


def test_ambiguous_espn_doubleheader_key_leaves_both_none():
    games = [
        {"game_pk": 333, "away": "New York Mets", "home": "Atlanta Braves"},
        {"game_pk": 334, "away": "New York Mets", "home": "Atlanta Braves"},
    ]
    schedule = _schedule_body(games)
    # Two ESPN events share the SAME (date, team-pair) key -- a doubleheader.
    espn = _espn_body([("New York Mets", "Atlanta Braves"),
                        ("New York Mets", "Atlanta Braves")])
    kalshi = _kalshi_body([])
    http = _fake_http(schedule, espn, kalshi)

    rows = build_bridge("2026-07-03", http=http)
    assert len(rows) == 2
    for r in rows:
        assert r.espn_id is None  # never guess which half of the doubleheader


def test_kalshi_ticker_for_different_date_never_mismatches():
    games = [{"game_pk": 555, "away": "Boston Red Sox", "home": "Los Angeles Angels"}]
    schedule = _schedule_body(games)
    espn = _espn_body([])
    # Ticker's OWN encoded date (26JUL04) differs from the caller's date (2026-07-03).
    kalshi = _kalshi_body(["KXMLBGAME-26JUL042130BOSLAA"])
    http = _fake_http(schedule, espn, kalshi)

    rows = build_bridge("2026-07-03", http=http)
    assert len(rows) == 1
    assert rows[0].kalshi_ticker_stem is None


def test_feed_failure_returns_empty_rows_never_raises():
    http = lambda url: None  # noqa: E731 -- every feed fails
    rows = build_bridge("2026-07-03", http=http)
    assert rows == []


# ---------------------------------------------------------------------------
# S1e ticker-resolution defect (2026-09-01): the EVENT stem's /orderbook returns
# 200 with empty ladders; only per-side MARKET tickers carry a book, so the
# bridge must surface them.
# ---------------------------------------------------------------------------
def test_bridge_surfaces_per_side_market_tickers_not_just_the_stem():
    stem = "KXMLBGAME-26JUL031805STLCHC"
    games = [{"game_pk": 111, "away": "St. Louis Cardinals", "home": "Chicago Cubs"}]
    kalshi = {"markets": [{"ticker": stem + "-STL", "event_ticker": stem},
                          {"ticker": stem + "-CHC", "event_ticker": stem}]}
    http = _fake_http(_schedule_body(games),
                      _espn_body([("St. Louis Cardinals", "Chicago Cubs")]), kalshi)

    r = build_bridge("2026-07-03", http=http)[0]
    assert r.kalshi_ticker_stem == stem
    assert r.kalshi_market_tickers == (stem + "-CHC", stem + "-STL")
    assert stem not in r.kalshi_market_tickers, "the stem is an event id, not a market"


def test_unresolved_stem_leaves_market_tickers_empty():
    games = [{"game_pk": 111, "away": "St. Louis Cardinals", "home": "Chicago Cubs"}]
    http = _fake_http(_schedule_body(games), _espn_body([]), {"markets": []})
    r = build_bridge("2026-07-03", http=http)[0]
    assert r.kalshi_ticker_stem is None and r.kalshi_market_tickers == ()
