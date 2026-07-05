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


# ---------------------------------------------------------------------------
# Soccer 1X2 draw-leg plumbing (PROPOSED_soccer_1x2_close_proxy_devig.md)
# ---------------------------------------------------------------------------

def test_odds_index_carries_draw_leg_through(monkeypatch):
    """A raw 3-way soccer event's 'draw' price must survive _lookup's re-key by
    team label -- previously silently dropped (root cause of the arb-guard bug)."""
    import scripts.platformkit.pm_trading.paper_today_support as mod

    def _fake_aggregate(sport):
        return {"sport": sport, "status": "ok", "events": [
            {"event_id": "evt-9", "sport": sport, "home": "Austria",
             "away": "Jordan", "commence_time": "2026-07-04T18:00Z",
             "prices": {"bookA": {"home": 1.3922, "away": 9.0, "draw": 4.5}}},
        ]}

    monkeypatch.setattr(mod, "aggregate", _fake_aggregate)
    lookup, _ = S.odds_index("soccer_intl")
    prices = lookup("soccer_intl", "Austria", "Jordan")
    assert prices is not None
    assert prices["bookA"]["Austria"] == 1.3922
    assert prices["bookA"]["Jordan"] == 9.0
    assert prices["bookA"]["draw"] == 4.5


def test_odds_index_no_draw_leg_for_twoway_sport(monkeypatch):
    """mlb/nba/wnba moneyline books never carry 'draw' -> key stays absent,
    behavior is byte-identical to before this fix."""
    import scripts.platformkit.pm_trading.paper_today_support as mod

    def _fake_aggregate(sport):
        return {"sport": sport, "status": "ok", "events": [
            {"event_id": "evt-10", "sport": sport, "home": "Boston Red Sox",
             "away": "Toronto Blue Jays", "commence_time": "2026-07-04T23:00Z",
             "prices": {"stub_book": {"home": 1.95, "away": 1.90}}},
        ]}

    monkeypatch.setattr(mod, "aggregate", _fake_aggregate)
    lookup, _ = S.odds_index("mlb")
    prices = lookup("mlb", "Boston Red Sox", "Toronto Blue Jays")
    assert "draw" not in prices["stub_book"]


def test_close_proxy_draw_decimal_worst_across_books():
    book_prices = {"bookA": {"home": 1.3922, "away": 9.0, "draw": 4.5},
                  "bookB": {"home": 1.40, "away": 8.5, "draw": 4.2}}
    assert S.close_proxy_draw_decimal(book_prices) == 4.2  # min = worst price


def test_close_proxy_draw_decimal_none_when_no_draw_leg():
    assert S.close_proxy_draw_decimal({"stub_book": {"home": 1.95, "away": 1.90}}) is None
    assert S.close_proxy_draw_decimal(None) is None
    assert S.close_proxy_draw_decimal({}) is None


# ---------------------------------------------------------------------------
# prediction-logger hygiene: dedup on EVENT day, not LOG day.
# ---------------------------------------------------------------------------

def test_prediction_event_day_uses_commence_time_over_logged_at():
    row = {"commence_time": "2026-07-01T23:00:00Z", "logged_at": "2026-07-03T02:00:00Z"}
    assert S.prediction_event_day(row) == "2026-07-01"


def test_prediction_event_day_falls_back_to_logged_at_when_no_commence():
    row = {"commence_time": "", "logged_at": "2026-07-03T02:00:00Z"}
    assert S.prediction_event_day(row) == "2026-07-03"


def test_prediction_event_day_explicit_fallback_wins_over_logged_at():
    row = {"commence_time": None, "logged_at": "2026-07-03T02:00:00Z"}
    assert S.prediction_event_day(row, fallback_day="2026-07-04") == "2026-07-04"


def test_prediction_keys_dedup_by_event_day_not_log_day():
    """THE regression: two rows for the SAME game (same commence_time) but
    logged on DIFFERENT calendar days (a finished game re-seen the next day)
    must collapse to ONE dedup key, not two."""
    rows = [
        {"sport": "mlb", "matchup": "Toronto Blue Jays@Boston Red Sox",
         "selection": "Boston Red Sox", "commence_time": "2026-07-01T23:00:00Z",
         "logged_at": "2026-07-01T20:00:00Z"},
        {"sport": "mlb", "matchup": "Toronto Blue Jays@Boston Red Sox",
         "selection": "Boston Red Sox", "commence_time": "2026-07-01T23:00:00Z",
         "logged_at": "2026-07-03T02:00:00Z"},  # same game, logged 2 days later
    ]
    keys = S.prediction_keys(rows)
    assert len(keys) == 1  # collapsed -- would have been 2 under the old logged_at key
