"""tests/platformkit/test_espn_spread_total.py -- NETWORK-FREE tests for
ESPN spread + total parsing in odds_provider.espn.parse_pickcenter and the
round-trip through markets.quotes_from_aggregate.

Run ONLY this file (a bare pytest freezes the box):
    python -m pytest tests/platformkit/test_espn_spread_total.py -q
"""
from __future__ import annotations

import math
from typing import Any, Dict

from scripts.platformkit.odds_provider.espn import (
    EspnProvider, parse_pickcenter, _spread_node, _total_node)
from scripts.platformkit.odds_provider.markets import (
    MONEYLINE, SPREAD, TOTAL, MarketQuote, quotes_from_aggregate)
from scripts.platformkit.odds_provider.base import american_to_decimal

# ---------------------------------------------------------------------------
# Canned pickcenter payloads (fully offline)
# ---------------------------------------------------------------------------

# Full: moneyline + spread (with spreadOdds) + total (with over/underOdds).
_FULL_PC = {
    "pickcenter": [{
        "provider": {"name": "DraftKings"},
        "homeTeamOdds": {"moneyLine": -198, "spreadOdds": -110},
        "awayTeamOdds": {"moneyLine": 164,  "spreadOdds": -110},
        "spread": -5.5,
        "overUnder": 220.5,
        "overOdds": -108,
        "underOdds": -112,
    }]
}

# Moneyline-only (no spread / overUnder fields).
_ML_ONLY_PC = {
    "pickcenter": [{
        "provider": {"name": "FanDuel"},
        "homeTeamOdds": {"moneyLine": -175},
        "awayTeamOdds": {"moneyLine": 144},
    }]
}

# Spread line present but spreadOdds absent; total line present but prices absent.
_LINE_NO_PRICE_PC = {
    "pickcenter": [{
        "provider": {"name": "BetMGM"},
        "homeTeamOdds": {"moneyLine": -200},
        "awayTeamOdds": {"moneyLine": 168},
        "spread": -6.5,
        "overUnder": 215.5,
    }]
}

# Only ONE side's spreadOdds present -> spread must be omitted.
_ONE_SIDE_SPREAD_PC = {
    "pickcenter": [{
        "provider": {"name": "ESPN BET"},
        "homeTeamOdds": {"moneyLine": -180, "spreadOdds": -110},
        "awayTeamOdds": {"moneyLine": 150},
        "spread": -4.5,
    }]
}

# Two books: first ML-only, second full (spread + total).
_MULTI_BOOK_PC = {
    "pickcenter": [
        {
            "provider": {"name": "Caesars"},
            "homeTeamOdds": {"moneyLine": -200},
            "awayTeamOdds": {"moneyLine": 168},
        },
        {
            "provider": {"name": "DraftKings"},
            "homeTeamOdds": {"moneyLine": -195, "spreadOdds": -110},
            "awayTeamOdds": {"moneyLine": 160,  "spreadOdds": -110},
            "spread": -5.5,
            "overUnder": 222.0,
            "overOdds": -110,
            "underOdds": -110,
        },
    ]
}

# Malformed first entry (no provider), valid second entry.
_MALFORMED_THEN_GOOD_PC = {
    "pickcenter": [
        {"provider": None, "homeTeamOdds": {"moneyLine": -200}},
        {
            "provider": {"name": "DraftKings"},
            "homeTeamOdds": {"moneyLine": -180, "spreadOdds": -110},
            "awayTeamOdds": {"moneyLine": 155,  "spreadOdds": -110},
            "spread": -4.5,
            "overUnder": 218.0,
            "overOdds": -110,
            "underOdds": -110,
        },
    ]
}

_HOME = "San Antonio Spurs"
_AWAY = "New York Knicks"


def _q(quotes, market_type, side, book):
    matches = [q for q in quotes
               if q.market_type == market_type and q.side == side
               and q.book == book]
    return matches[0] if matches else None


def _make_agg(prices: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a prices dict into a minimal aggregate() payload for injection."""
    return {
        "sport": "nba",
        "status": "ok",
        "as_of": "2026-06-18T20:00:00+00:00",
        "events": [{
            "event_id": "401",
            "sport": "nba",
            "home": _HOME,
            "away": _AWAY,
            "prices": prices,
        }],
    }


# ---------------------------------------------------------------------------
# Unit tests: parse_pickcenter output shape
# ---------------------------------------------------------------------------

def test_full_payload_spread_and_total_values():
    """Full pickcenter -> spread node with correct line/odds, total with over/under."""
    out = parse_pickcenter(_FULL_PC, _HOME, _AWAY)
    v = out["espn:DraftKings"]
    assert "spread" in v and "total" in v
    sp = v["spread"]
    assert sp["home"]["line"] == -5.5 and sp["away"]["line"] == 5.5
    assert math.isclose(sp["home"]["odds"], american_to_decimal(-110))
    assert math.isclose(sp["away"]["odds"], american_to_decimal(-110))
    tot = v["total"]
    assert tot["over"]["line"] == 220.5 and tot["under"]["line"] == 220.5
    assert math.isclose(tot["over"]["odds"],  american_to_decimal(-108))
    assert math.isclose(tot["under"]["odds"], american_to_decimal(-112))


def test_moneyline_unchanged_by_spread_total_addition():
    """Moneyline decimal conversion is byte-identical to the pre-change behaviour."""
    out = parse_pickcenter(_FULL_PC, _HOME, _AWAY)
    v = out["espn:DraftKings"]
    assert math.isclose(v["home"], american_to_decimal(-198))
    assert math.isclose(v["away"], american_to_decimal(164))


def test_ml_only_payload_no_spread_total_keys():
    """ML-only payload produces only moneyline keys; spread/total absent."""
    out = parse_pickcenter(_ML_ONLY_PC, _HOME, _AWAY)
    v = out["espn:FanDuel"]
    assert math.isclose(v["home"], american_to_decimal(-175))
    assert math.isclose(v["away"], american_to_decimal(144))
    assert "spread" not in v and "total" not in v


def test_spread_omitted_when_no_spread_odds():
    """Spread line present but NO spreadOdds -> spread absent; moneyline intact."""
    out = parse_pickcenter(_LINE_NO_PRICE_PC, _HOME, _AWAY)
    v = out["espn:BetMGM"]
    assert "spread" not in v, "must NOT fabricate a spread price"
    assert "total" not in v, "must NOT fabricate a total price"
    assert "home" in v and "away" in v


def test_spread_omitted_when_only_one_side_has_odds():
    """One-sided spreadOdds -> whole spread node is omitted (no devig on partial)."""
    out = parse_pickcenter(_ONE_SIDE_SPREAD_PC, _HOME, _AWAY)
    assert "spread" not in out["espn:ESPN BET"]


def test_multi_book_selective_spread_total():
    """First book (ML-only) has no spread/total; second book (full) has both."""
    out = parse_pickcenter(_MULTI_BOOK_PC, _HOME, _AWAY)
    assert "spread" not in out["espn:Caesars"] and "total" not in out["espn:Caesars"]
    assert "spread" in out["espn:DraftKings"] and "total" in out["espn:DraftKings"]


def test_malformed_entry_skipped_good_entry_survives():
    """Entry with no provider is skipped; subsequent good entry is populated."""
    out = parse_pickcenter(_MALFORMED_THEN_GOOD_PC, _HOME, _AWAY)
    assert len(out) == 1
    assert "espn:DraftKings" in out
    assert "spread" in out["espn:DraftKings"] and "total" in out["espn:DraftKings"]


# ---------------------------------------------------------------------------
# Unit tests: _spread_node and _total_node helpers
# ---------------------------------------------------------------------------

def test_spread_node_requires_line():
    assert _spread_node({"homeTeamOdds": {"spreadOdds": -110},
                         "awayTeamOdds": {"spreadOdds": -110}}) is None


def test_spread_node_pick_em_zero_is_valid():
    """Spread=0 is a valid pick-em line; node is produced (not treated as absent)."""
    node = _spread_node({"spread": 0,
                         "homeTeamOdds": {"spreadOdds": -110},
                         "awayTeamOdds": {"spreadOdds": -110}})
    assert node is not None
    assert node["home"]["line"] == 0.0 and node["away"]["line"] == 0.0


def test_total_node_requires_both_sides():
    assert _total_node({"overOdds": -110, "underOdds": -110}) is None   # no line
    assert _total_node({"overUnder": 220.5}) is None                     # no prices
    assert _total_node({"overUnder": 220.5, "overOdds": -110}) is None  # under missing
    assert _total_node({"overUnder": 220.5, "underOdds": -110}) is None # over missing


# ---------------------------------------------------------------------------
# Integration: round-trip through markets.quotes_from_aggregate
# ---------------------------------------------------------------------------

def _full_prices() -> Dict[str, Any]:
    return parse_pickcenter(_FULL_PC, _HOME, _AWAY)


def test_roundtrip_spread_and_total_quotes():
    """quotes_from_aggregate produces SPREAD + TOTAL MarketQuotes from ESPN data."""
    agg = _make_agg(_full_prices())
    quotes = quotes_from_aggregate("nba", agg=agg)
    h = _q(quotes, SPREAD, "home", "espn:DraftKings")
    a = _q(quotes, SPREAD, "away", "espn:DraftKings")
    assert h is not None and h.line == -5.5
    assert a is not None and a.line == 5.5
    assert math.isclose(h.odds, american_to_decimal(-110))
    assert h.devigged_prob is not None and 0.0 < h.devigged_prob < 1.0
    over  = _q(quotes, TOTAL, "over",  "espn:DraftKings")
    under = _q(quotes, TOTAL, "under", "espn:DraftKings")
    assert over is not None and over.line == 220.5
    assert under is not None and under.line == 220.5
    assert math.isclose(over.odds,  american_to_decimal(-108))
    assert math.isclose(under.odds, american_to_decimal(-112))
    assert over.devigged_prob is not None and 0.0 < over.devigged_prob < 1.0


def test_roundtrip_moneyline_still_present():
    """Moneyline MarketQuotes survive alongside spread + total."""
    agg = _make_agg(_full_prices())
    quotes = quotes_from_aggregate("nba", agg=agg)
    h = _q(quotes, MONEYLINE, "home", "espn:DraftKings")
    a = _q(quotes, MONEYLINE, "away", "espn:DraftKings")
    assert h is not None and math.isclose(h.odds, american_to_decimal(-198))
    assert a is not None and math.isclose(a.odds, american_to_decimal(164))


def test_roundtrip_ml_only_no_spread_total_quotes():
    """ML-only ESPN payload: quotes_from_aggregate yields no SPREAD/TOTAL quotes."""
    agg = _make_agg(parse_pickcenter(_ML_ONLY_PC, _HOME, _AWAY))
    quotes = quotes_from_aggregate("nba", agg=agg)
    assert not any(q.market_type == SPREAD for q in quotes)
    assert not any(q.market_type == TOTAL  for q in quotes)
    assert any(q.market_type == MONEYLINE  for q in quotes)


def test_roundtrip_line_no_price_no_spread_total_quotes():
    """Spread/total lines present but prices absent: no SPREAD/TOTAL quotes emitted."""
    agg = _make_agg(parse_pickcenter(_LINE_NO_PRICE_PC, _HOME, _AWAY))
    quotes = quotes_from_aggregate("nba", agg=agg)
    assert not any(q.market_type == SPREAD for q in quotes)
    assert not any(q.market_type == TOTAL  for q in quotes)
    assert any(q.market_type == MONEYLINE  for q in quotes)
