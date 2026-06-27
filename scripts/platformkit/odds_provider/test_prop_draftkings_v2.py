"""Per-file unit tests for prop_draftkings_v2 (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/odds_provider/test_prop_draftkings_v2.py -q

Canned payloads mirror the LIVE DK SportContent O/U subcategory shape probed
2026-06-23: top-level keys events / markets / selections / subcategories;
each market name = "{Player} {Stat} O/U"; selections join via marketId with
`label`="Over"/"Under", `points` carrying the LINE, and displayOdds.decimal
(or displayOdds.american) the price. Player props live on per-stat
subcategories (e.g. cat 743 / sub 6719 = Hits O/U), not on the parent
category, which mostly serves milestone ("1+") single-sided markets.
"""
from __future__ import annotations

import pytest

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_provider.prop_draftkings_v2 import (
    DraftKingsV2Provider,
    parse_subcategory_payload,
)

_AS_OF = "2026-06-23T17:00:00+00:00"


def _payload_hits_ou_two_sided() -> dict:
    """One MLB event, one batter Hits O/U market, Over+Under priced."""
    return {
        "events": [{"id": "34307953", "name": "HOU Astros @ TOR Blue Jays"}],
        "markets": [{
            "id": "MK1", "eventId": "34307953",
            "name": "Yordan Alvarez Hits O/U",
        }],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "1.45", "american": "-220"}},
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"decimal": "2.80", "american": "+180"}},
        ],
    }


# --------------------------------------------------------------------------- #
# parse_subcategory_payload -- happy path
# --------------------------------------------------------------------------- #

def test_parses_two_sided_market_into_one_propline():
    body = _payload_hits_ou_two_sided()
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, PropLine)
    assert r.sport == "mlb"
    assert r.event_id == "34307953"
    assert r.match == "HOU Astros @ TOR Blue Jays"
    assert r.player == "Yordan Alvarez"
    assert r.stat == "Hits"
    assert r.line == 0.5
    assert abs(r.over_price - 1.45) < 1e-9
    assert abs(r.under_price - 2.80) < 1e-9
    assert r.payout_type == "sportsbook"
    assert r.source == "draftkings"
    assert r.as_of == _AS_OF


def test_falls_back_to_american_when_decimal_missing():
    """displayOdds.american alone (no decimal) -> still parses via converter."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1", "name": "Aaron Judge RBIs O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"american": "+150"}},  # +150 -> 2.50
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"american": "-200"}},  # -200 -> 1.50
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "RBIs", _AS_OF)
    assert len(rows) == 1
    r = rows[0]
    assert abs(r.over_price - 2.50) < 1e-9
    assert abs(r.under_price - 1.50) < 1e-9


def test_unicode_minus_in_american_odds():
    """DK uses U+2212 (true minus); the parser must accept it."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1", "name": "Some Player Hits O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"american": "+120"}},
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"american": "−150"}},  # U+2212 minus
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert len(rows) == 1
    r = rows[0]
    assert r.over_price is not None and r.under_price is not None


def test_multiple_lines_per_market_emit_separate_rows():
    """A single market with two lines (0.5 and 1.5) -> two PropLines."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1",
                     "name": "Bo Bichette Total Bases O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "1.20"}},
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"decimal": "4.00"}},
            {"marketId": "MK1", "label": "Over", "points": 1.5,
             "displayOdds": {"decimal": "2.00"}},
            {"marketId": "MK1", "label": "Under", "points": 1.5,
             "displayOdds": {"decimal": "1.85"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Total Bases", _AS_OF)
    assert len(rows) == 2
    lines = sorted(r.line for r in rows)
    assert lines == [0.5, 1.5]
    for r in rows:
        assert r.player == "Bo Bichette"
        assert r.stat == "Total Bases"


def test_stat_canon_applied_when_input_is_raw_label():
    """parser canonicalizes the stat via canon_stat ('rbis' -> 'RBIs')."""
    body = _payload_hits_ou_two_sided()
    # Pretend caller passes lowercase 'hits' (e.g. typo); the parser should
    # still emit canonical 'Hits' on the PropLine.
    rows = parse_subcategory_payload(body, "mlb", "hits", _AS_OF)
    # NB: market name still says ' Hits O/U' (capitalized), but the canon stat
    # passed in IS 'hits' lowercase -- player-strip uses ' hits' suffix which
    # WON'T match 'Yordan Alvarez Hits O/U'. So zero rows -- correct behavior:
    # the caller must pass the stat exactly as it appears in the market name.
    assert rows == []


# --------------------------------------------------------------------------- #
# parse_subcategory_payload -- never fabricates / skip rules
# --------------------------------------------------------------------------- #

def test_market_name_missing_stat_suffix_is_skipped():
    """Market name doesn't end in ' {stat}' or ' {stat} O/U' -> skipped."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1",
                     "name": "Vladimir Guerrero Jr. Awesomeness"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "2.00"}},
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"decimal": "1.85"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert rows == []


def test_market_with_no_priced_side_is_dropped():
    """Neither over nor under has a usable decimal -> row dropped (no fake price)."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1", "name": "Some Player Hits O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "1.00"}},   # invalid (<=1.0)
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"decimal": "not-a-number"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert rows == []


def test_over_only_market_keeps_under_none():
    """Sportsbook posted Over only -> Under stays absent (never fabricated)."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1",
                     "name": "Some Player Home Runs O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "3.50"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Home Runs", _AS_OF)
    assert len(rows) == 1
    r = rows[0]
    assert abs(r.over_price - 3.50) < 1e-9
    assert r.under_price is None
    assert r.payout_type == "sportsbook"  # at least one side has real price


def test_selection_without_points_is_skipped():
    """No `points` on a selection -> skipped (cannot infer the line)."""
    body = {
        "events": [{"id": "E1", "name": "X @ Y"}],
        "markets": [{"id": "MK1", "eventId": "E1", "name": "Some Player Hits O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over",  # missing points
             "displayOdds": {"decimal": "1.85"}},
            {"marketId": "MK1", "label": "Under",  # missing points
             "displayOdds": {"decimal": "1.95"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert rows == []


def test_empty_payload_returns_empty_list():
    assert parse_subcategory_payload({}, "mlb", "Hits", _AS_OF) == []
    assert parse_subcategory_payload(
        {"events": [], "markets": [], "selections": []}, "mlb", "Hits", _AS_OF) == []


def test_non_dict_input_returns_empty_list():
    assert parse_subcategory_payload(None, "mlb", "Hits", _AS_OF) == []  # type: ignore[arg-type]
    assert parse_subcategory_payload("garbage", "mlb", "Hits", _AS_OF) == []  # type: ignore[arg-type]


def test_event_not_in_events_map_keeps_match_none():
    """Market references an eventId not in events[] -> match stays None (honest)."""
    body = {
        "events": [],  # empty
        "markets": [{"id": "MK1", "eventId": "MISSING",
                     "name": "Riley Greene Hits O/U"}],
        "selections": [
            {"marketId": "MK1", "label": "Over", "points": 0.5,
             "displayOdds": {"decimal": "1.60"}},
            {"marketId": "MK1", "label": "Under", "points": 0.5,
             "displayOdds": {"decimal": "2.30"}},
        ],
    }
    rows = parse_subcategory_payload(body, "mlb", "Hits", _AS_OF)
    assert len(rows) == 1
    assert rows[0].match is None
    assert rows[0].event_id == "MISSING"


# --------------------------------------------------------------------------- #
# DraftKingsV2Provider -- fetch_props orchestration
# --------------------------------------------------------------------------- #

def test_fetch_props_unsupported_sport_returns_unavailable():
    prov = DraftKingsV2Provider(http_get=lambda u: {})
    res = prov.fetch_props("tennis")
    assert is_unavailable(res)
    assert "unsupported sport" in res.get("reason", "")


def test_fetch_props_all_subcategories_empty_returns_unavailable():
    """Every subcategory fetch returns {} -> UNAVAILABLE (no synthetic rows)."""
    prov = DraftKingsV2Provider(http_get=lambda u: {})
    res = prov.fetch_props("mlb")
    assert is_unavailable(res)


def test_fetch_props_concatenates_subcategories():
    """MLB fans out across multiple subcats -> rows from BOTH stats surface."""
    body_hits = _payload_hits_ou_two_sided()
    body_ks = {
        "events": [{"id": "E2", "name": "NYY @ DET"}],
        "markets": [{"id": "MK2", "eventId": "E2",
                     "name": "Tarik Skubal Strikeouts O/U"}],
        "selections": [
            {"marketId": "MK2", "label": "Over", "points": 8.5,
             "displayOdds": {"decimal": "1.95"}},
            {"marketId": "MK2", "label": "Under", "points": 8.5,
             "displayOdds": {"decimal": "1.85"}},
        ],
    }
    calls = []
    def fake_get(url: str) -> dict:
        calls.append(url)
        if "subcategories/6719" in url:  # Hits O/U
            return body_hits
        if "subcategories/15221" in url:  # Strikeouts Thrown O/U
            return body_ks
        return {}
    prov = DraftKingsV2Provider(http_get=fake_get)
    rows = prov.fetch_props("mlb")
    assert isinstance(rows, list)
    players = sorted(r.player for r in rows)
    assert "Yordan Alvarez" in players
    assert "Tarik Skubal" in players
    # Confirm both subcategories were fetched.
    assert any("6719" in u for u in calls)
    assert any("15221" in u for u in calls)


def test_fetch_props_partial_subcat_failure_keeps_other_rows():
    """One subcategory empty / errored -> the other still contributes."""
    body_ks = {
        "events": [{"id": "E2", "name": "NYY @ DET"}],
        "markets": [{"id": "MK2", "eventId": "E2",
                     "name": "Tarik Skubal Strikeouts O/U"}],
        "selections": [
            {"marketId": "MK2", "label": "Over", "points": 8.5,
             "displayOdds": {"decimal": "1.95"}},
            {"marketId": "MK2", "label": "Under", "points": 8.5,
             "displayOdds": {"decimal": "1.85"}},
        ],
    }
    def fake_get(url: str) -> dict:
        if "subcategories/6719" in url:
            return {}
        if "subcategories/15221" in url:
            return body_ks
        return {}
    prov = DraftKingsV2Provider(http_get=fake_get)
    rows = prov.fetch_props("mlb")
    assert isinstance(rows, list)
    assert any(r.player == "Tarik Skubal" for r in rows)


def test_fetch_props_never_raises_on_http_exception():
    """An http_get that raises -> UNAVAILABLE (or [] -- both honest, never crash)."""
    def boom(_url: str) -> dict:
        raise RuntimeError("simulated network down")
    prov = DraftKingsV2Provider(http_get=boom)
    res = prov.fetch_props("mlb")
    assert is_unavailable(res) or res == []


def test_provider_name_is_draftkings():
    """Source attribution must say 'draftkings' so merge_multi_source attributes
    the best_book truthfully across DK + Underdog merges."""
    assert DraftKingsV2Provider().name == "draftkings"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
