"""Tests for the keyless FanDuel moneyline provider. Per-file:
python -m pytest scripts/platformkit/odds_provider/test_fanduel.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.fanduel import (
    FanDuelProvider, parse_moneylines)

_PAYLOAD = {
    "attachments": {
        "events": {
            "100": {"name": "New York Yankees (C Schlittler) @ Boston Red Sox (C Early)",
                    "openDate": "2026-06-26T23:05:00Z"},
            "200": {"name": "Texas Rangers (TBD) @ Toronto Blue Jays (TBD)"},
        },
        "markets": {
            "m1": {"eventId": 100, "marketType": "MONEY_LINE", "runners": [
                {"runnerName": "New York Yankees",
                 "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.67}}}},
                {"runnerName": "Boston Red Sox",
                 "winRunnerOdds": {"americanDisplayOdds": {"americanOddsInt": 126}}},
            ]},
            "m2": {"eventId": 200, "marketType": "TOTAL_POINTS_(OVER/UNDER)",
                   "runners": []},  # not a moneyline -> ignored
            "m3": {"eventId": 200, "marketType": "MONEY_LINE", "runners": [
                {"runnerName": "Texas Rangers",
                 "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.89}}}},
                # missing the second team -> market skipped (never half-filled)
            ]},
        },
    }
}


def test_parse_moneylines_extracts_two_way():
    evs = parse_moneylines(_PAYLOAD, "mlb")
    assert len(evs) == 1  # m2 not ML, m3 half-filled -> only m1
    e = evs[0]
    assert e.home == "Boston Red Sox" and e.away == "New York Yankees"
    assert e.prices["fanduel"]["away"] == 1.67
    # american +126 -> decimal 2.26
    assert abs(e.prices["fanduel"]["home"] - 2.26) < 0.01
    assert e.source == "fanduel"


def test_half_filled_market_skipped():
    evs = parse_moneylines(_PAYLOAD, "mlb")
    assert all("home" in e.prices["fanduel"] and "away" in e.prices["fanduel"]
               for e in evs)


def test_fetch_uses_injected_http_get():
    p = FanDuelProvider(http_get=lambda url: _PAYLOAD)
    evs = p.fetch("mlb")
    assert isinstance(evs, list) and len(evs) == 1


def test_unsupported_sport_unavailable():
    p = FanDuelProvider(http_get=lambda url: _PAYLOAD)
    res = p.fetch("cricket")
    assert isinstance(res, dict) and "unsupported" in res.get("reason", "")


def test_empty_payload_unavailable():
    p = FanDuelProvider(http_get=lambda url: {})
    res = p.fetch("mlb")
    assert isinstance(res, dict) and res.get("reason")


# --- WNBA (LANE 2): customPageId="wnba" probed live 2026-07-03, real payload
# shape captured below (team names have no "(pitcher)" parens to strip). ---
_WNBA_PAYLOAD = {
    "attachments": {
        "events": {
            "300": {"name": "Golden State Valkyries @ Atlanta Dream",
                    "openDate": "2026-07-04T17:00:00Z"},
        },
        "markets": {
            "w1": {"eventId": 300, "marketType": "MONEY_LINE", "runners": [
                {"runnerName": "Golden State Valkyries",
                 "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 2.10}}}},
                {"runnerName": "Atlanta Dream",
                 "winRunnerOdds": {"trueOdds": {"decimalOdds": {"decimalOdds": 1.80}}}},
            ]},
        },
    }
}


def test_wnba_page_id_wired_and_parses():
    p = FanDuelProvider(http_get=lambda url: _WNBA_PAYLOAD)
    evs = p.fetch("wnba")
    assert isinstance(evs, list) and len(evs) == 1
    e = evs[0]
    assert e.away == "Golden State Valkyries" and e.home == "Atlanta Dream"
    assert e.prices["fanduel"]["away"] == 2.10
    assert e.prices["fanduel"]["home"] == 1.80


def test_wnba_page_id_in_page_map():
    from scripts.platformkit.odds_provider.fanduel import _PAGE
    assert _PAGE["wnba"] == "wnba"
