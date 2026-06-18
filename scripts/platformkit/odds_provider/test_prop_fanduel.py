"""Per-file unit tests for prop_fanduel (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_fanduel.py -q

Canned payloads mirror the REAL FanDuel shapes probed 2026-06-17 (trimmed). Two
cases are exercised:
  1. The CURRENT live state -- events posted but only Moneyline/Penalty markets,
     NO player props -> the provider degrades to unavailable("no player-prop ...").
  2. A future prop market in the SAME real runner shape -> two-way priced rows.
http_get is injected; nothing here touches the network.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_fanduel import (
    FanDuelProvider, list_event_ids, parse_event_props)

# content-managed page: one real match event + the tournament-outright event.
PAGE = {
    "attachments": {"events": {
        "35035171": {"name": "Uzbekistan v Colombia",
                     "openDate": "2026-06-18T02:00:00.000Z", "eventTypeId": 1},
        "31345701": {"name": "FIFA World Cup", "eventTypeId": 1},  # outright
    }}
}

# CURRENT live state: only Moneyline + Penalty markets (no player props).
EVENT_NO_PROPS = {
    "attachments": {
        "events": {"35035171": {"name": "Uzbekistan v Colombia"}},
        "markets": {
            "M1": {"marketId": "M1", "eventId": "35035171",
                   "marketName": "Moneyline (3-way)",
                   "runners": [
                       {"runnerName": "Uzbekistan", "handicap": 0,
                        "winRunnerOdds": {"americanDisplayOdds": {
                            "americanOdds": 1000}}},
                       {"runnerName": "Colombia", "handicap": 0,
                        "winRunnerOdds": {"americanDisplayOdds": {
                            "americanOdds": -320}}}]},
            "M2": {"marketId": "M2", "eventId": "35035171",
                   "marketName": "Penalty Awarded?",
                   "runners": [{"runnerName": "Yes", "handicap": 0,
                                "winRunnerOdds": {"americanDisplayOdds": {
                                    "americanOdds": 182}}}]},
        },
    }
}

# FUTURE prop market in the SAME real runner shape (Over/Under + handicap line).
EVENT_WITH_PROPS = {
    "attachments": {
        "events": {"35035171": {"name": "Uzbekistan v Colombia"}},
        "markets": {
            "P1": {"marketId": "P1", "eventId": "35035171",
                   "marketName": "Luis Diaz - Shots on Target",
                   "runners": [
                       {"runnerName": "Over", "handicap": 1.5,
                        "winRunnerOdds": {"americanDisplayOdds": {
                            "americanOdds": 120}}},
                       {"runnerName": "Under", "handicap": 1.5,
                        "winRunnerOdds": {"americanDisplayOdds": {
                            "americanOdds": -150}}}]},
        },
    }
}


def test_list_event_ids_filters_outrights():
    ids = list_event_ids(PAGE)
    assert ids == ["35035171"]  # outright "FIFA World Cup" excluded


def test_parse_no_props_returns_empty():
    assert parse_event_props(EVENT_NO_PROPS, "soccer_intl") == []


def test_parse_props_two_way_priced():
    rows = parse_event_props(EVENT_WITH_PROPS, "soccer_intl")
    assert len(rows) == 1
    r = rows[0]
    assert r.stat == "Shots On Target"
    assert r.line == 1.5
    assert r.match == "Uzbekistan v Colombia"
    assert r.payout_type == "sportsbook"
    assert r.source == "fanduel"
    # +120 -> 2.20 ; -150 -> 1.666...
    assert abs(r.over_price - 2.20) < 1e-9
    assert abs(r.under_price - (1.0 + 100.0 / 150.0)) < 1e-9
    assert r.as_of is not None


def test_provider_degrades_when_no_props():
    def http_get(url):
        return PAGE if "content-managed-page" in url else EVENT_NO_PROPS

    prov = FanDuelProvider(http_get=http_get)
    res = prov.fetch_props("soccer_intl")
    assert is_unavailable(res)
    assert "player-prop" in res.get("reason", "")


def test_provider_returns_priced_rows_when_posted():
    def http_get(url):
        return PAGE if "content-managed-page" in url else EVENT_WITH_PROPS

    prov = FanDuelProvider(http_get=http_get)
    rows = prov.fetch_props("soccer_intl")
    assert isinstance(rows, list)
    assert all(r.payout_type == "sportsbook" for r in rows)
    assert all(r.over_price and r.over_price > 1.0 for r in rows)


def test_unsupported_sport_unavailable():
    prov = FanDuelProvider(http_get=lambda url: PAGE)
    assert is_unavailable(prov.fetch_props("cricket"))


def test_injected_failure_degrades_no_raise():
    def boom(url):
        raise RuntimeError("network down")

    prov = FanDuelProvider(http_get=boom)
    assert is_unavailable(prov.fetch_props("soccer_intl"))


def test_empty_page_unavailable():
    prov = FanDuelProvider(http_get=lambda url: {})
    assert is_unavailable(prov.fetch_props("soccer_intl"))
