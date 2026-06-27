"""Tests for prop_draftkings_live -- LIVE in-play DK player props from the event endpoint.

Offline: the DK HTTP calls are injected. Pins event discovery (STARTED only), the two-way
O/U parse (player/stat split + line + both prices), and the no-half-fill / no-guess skips.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import prop_draftkings_live as L
from scripts.platformkit.odds_provider.prop_base import PropLine


def _league_payload():
    return {"events": [
        {"id": 111, "name": "TEX Rangers @ MIA Marlins", "status": "STARTED"},
        {"id": 222, "name": "BOS @ NYY", "status": "NOT_STARTED"},
    ]}


def _sel(mid, label, points, dec):
    return {"marketId": mid, "label": label, "points": points,
            "displayOdds": {"decimal": dec}}


def _event_payload():
    return {
        "markets": [
            {"id": 1, "name": "Wyatt Langford Hits + Runs + RBIs O/U"},
            {"id": 2, "name": "Jacob deGrom Strikeouts Thrown O/U"},
            {"id": 3, "name": "Otto Lopez Hits"},          # milestone (no Over/Under) -> skip
        ],
        "selections": [
            _sel(1, "Over", 3.5, "1.83"), _sel(1, "Under", 3.5, "1.86"),
            _sel(2, "Over", 7.5, "1.70"), _sel(2, "Under", 7.5, "2.10"),
            _sel(3, "2+", None, "1.95"),  # one-sided milestone
        ],
    }


def _http():
    def get(url):
        if url.endswith("/leagues/84240"):
            return _league_payload()
        if "/events/111/categories" in url:
            return _event_payload()
        return {}
    return get


def test_live_event_ids_started_only():
    ids = L.live_event_ids("mlb", http_get=_http())
    assert ids == ["111"]


def test_fetch_props_parses_two_way_ou_only():
    rows = L.fetch_props("mlb", http_get=_http())
    assert isinstance(rows, list)
    # only the 2 two-way O/U markets; the milestone "Otto Lopez Hits" is skipped
    assert len(rows) == 2
    by_player = {r.player: r for r in rows}
    hrr = by_player["Wyatt Langford"]
    assert isinstance(hrr, PropLine)
    assert hrr.stat == "Hits+Runs+RBIs" and hrr.line == 3.5
    assert hrr.over_price == 1.83 and hrr.under_price == 1.86
    assert hrr.payout_type == "sportsbook" and hrr.source == "draftkings_live"
    # "Strikeouts Thrown" canonicalizes to the box/repricer key "Pitcher Strikeouts"
    assert by_player["Jacob deGrom"].stat == "Pitcher Strikeouts"


def test_split_player_stat_longest_phrase_first():
    assert L._split_player_stat("Wyatt Langford Hits + Runs + RBIs O/U") == (
        "Wyatt Langford", "Hits+Runs+RBIs")
    assert L._split_player_stat("Otto Lopez Hits O/U") == ("Otto Lopez", "Hits")
    assert L._split_player_stat("Just A Header O/U") is None  # no known stat phrase


def test_unsupported_sport_is_unavailable():
    out = L.fetch_props("nhl", http_get=_http())
    assert isinstance(out, dict) and out.get("status") == "unavailable"


def test_half_filled_market_is_skipped():
    payload = {"markets": [{"id": 9, "name": "Some Guy Hits O/U"}],
               "selections": [_sel(9, "Over", 1.5, "1.90")]}  # Under missing
    rows = L._parse_event(payload, "111")
    assert rows == []  # never half-fill a two-way price


# --- soccer / World Cup readiness ----------------------------------------------
def test_split_player_stat_soccer_phrases():
    assert L._split_player_stat("Lionel Messi Shots On Target O/U", "soccer_intl") == (
        "Lionel Messi", "Shots On Target")
    assert L._split_player_stat("Cristiano Ronaldo Shots O/U", "soccer_intl") == (
        "Cristiano Ronaldo", "Shots")
    # "Shots on Goal" is DK phrasing for shots on target -> canonical override
    assert L._split_player_stat("Kylian Mbappe Shots on Goal O/U", "soccer_intl") == (
        "Kylian Mbappe", "Shots On Target")
    # an MLB phrase must NOT match under the soccer phrase set
    assert L._split_player_stat("Some Batter Hits O/U", "soccer_intl") is None


def test_soccer_parses_two_way_when_league_id_present(monkeypatch):
    # with the WC league id supplied (env-confirmed), a live two-way O/U parses cleanly.
    monkeypatch.setitem(L._LEAGUE, "soccer_intl", "40253")
    payload = {
        "markets": [{"id": 1, "name": "Cristiano Ronaldo Shots O/U"}],
        "selections": [_sel(1, "Over", 2.5, "1.90"), _sel(1, "Under", 2.5, "1.90")],
    }
    rows = L._parse_event(payload, "900001", sport="soccer_intl", match="POR @ ESP")
    assert len(rows) == 1
    assert rows[0].player == "Cristiano Ronaldo" and rows[0].stat == "Shots"
    assert rows[0].over_price == 1.90 and rows[0].under_price == 1.90


def test_soccer_unavailable_without_confirmed_league_id(monkeypatch):
    # no env league id wired -> honest unavailable (never a fabricated/guessed source).
    monkeypatch.delitem(L._LEAGUE, "soccer_intl", raising=False)
    out = L.fetch_props("soccer_intl", http_get=_http())
    assert isinstance(out, dict) and out.get("status") == "unavailable"
