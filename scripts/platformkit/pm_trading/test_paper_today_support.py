"""Per-file tests for scripts.platformkit.pm_trading.paper_today_support.

NO NETWORK: aggregate() is monkeypatched with canned OddsEvent-shaped dicts.
Covers the LANE 2 addition (wnba in DEFAULT_SPORTS) plus the odds_index /
event_meta / side_of / live_state helpers on WNBA's full-team-name shape
("Las Vegas Aces", not a short code) -- the same shape teams_match's nickname
fallback must resolve for a sport with no code resolver.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/pm_trading/test_paper_today_support.py -q
"""
from __future__ import annotations

from scripts.platformkit.pm_trading import paper_today_support as S


def test_default_sports_includes_wnba():
    assert "wnba" in S.DEFAULT_SPORTS
    # pre-existing sports untouched (additive only)
    assert set(S.DEFAULT_SPORTS) >= {"mlb", "soccer_intl", "nba", "tennis", "wnba"}


def test_odds_index_matches_wnba_full_team_names(monkeypatch):
    import scripts.platformkit.pm_trading.paper_today_support as mod

    def _fake_aggregate(sport):
        return {"sport": sport, "status": "ok", "events": [
            {"event_id": "evt-1", "sport": sport, "home": "Las Vegas Aces",
             "away": "Indiana Fever", "commence_time": "2026-07-04T23:00Z",
             "prices": {"kalshi": {"home": 1.45, "away": 3.10}}},
        ]}

    monkeypatch.setattr(mod, "aggregate", _fake_aggregate)
    lookup, events = S.odds_index("wnba")
    assert len(events) == 1
    prices = lookup("wnba", "Las Vegas Aces", "Indiana Fever")
    assert prices is not None
    assert prices["kalshi"]["Las Vegas Aces"] == 1.45
    assert prices["kalshi"]["Indiana Fever"] == 3.10


def test_odds_index_honest_none_when_no_match(monkeypatch):
    import scripts.platformkit.pm_trading.paper_today_support as mod

    def _fake_aggregate(sport):
        return {"sport": sport, "status": "ok", "events": [
            {"event_id": "evt-2", "sport": sport, "home": "Seattle Storm",
             "away": "Chicago Sky", "commence_time": None,
             "prices": {"kalshi": {"home": 1.9, "away": 1.9}}},
        ]}

    monkeypatch.setattr(mod, "aggregate", _fake_aggregate)
    lookup, events = S.odds_index("wnba")
    # a different game on the slate -> no fabricated match
    assert lookup("wnba", "Las Vegas Aces", "Indiana Fever") is None


def test_event_meta_wnba_full_names(monkeypatch):
    from scripts.platformkit.odds_provider.base import OddsEvent
    events = [OddsEvent(event_id="evt-3", sport="wnba", home="Las Vegas Aces",
                        away="Indiana Fever", commence_time="2026-07-04T23:00Z",
                        prices={})]
    meta = S.event_meta(events, "wnba", "Las Vegas Aces", "Indiana Fever")
    assert meta["event_id"] == "evt-3"
    assert meta["commence_time"] == "2026-07-04T23:00Z"
    # unmatched game -> empty strings, never fabricated
    empty = S.event_meta(events, "wnba", "Seattle Storm", "Chicago Sky")
    assert empty == {"event_id": "", "commence_time": ""}


def test_side_of_wnba_teams():
    assert S.side_of("Las Vegas Aces", "Las Vegas Aces", "Indiana Fever") == "home"
    assert S.side_of("Indiana Fever", "Las Vegas Aces", "Indiana Fever") == "away"
    assert S.side_of("Over 158.5", "Las Vegas Aces", "Indiana Fever") is None


def test_live_state_from_live_board_row():
    row_live = {"state": "in", "home_score": 55, "away_score": 50, "clock": "5:00"}
    row_pre = {"state": "pre", "home_score": None, "away_score": None, "clock": None}
    live = S.live_state(row_live)
    assert live is not None and live["home_score"] == 55
    assert S.live_state(row_pre) is None
