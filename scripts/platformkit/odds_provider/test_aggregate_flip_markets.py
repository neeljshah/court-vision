"""Per-file tests: aggregate merge carries spread/total across an orientation flip.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_aggregate_flip_markets.py -q

Acceptance:
  - When two providers report the same game with OPPOSITE home/away orientation,
    merge_events folds the second venue in flipped. The moneyline home/away swap,
    the SPREAD node's legs swap (and lines stay attached to their leg), and the
    TOTAL node (over/under) carries unchanged. Previously spread/total were dropped
    on a flip -- this guards that fix.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.aggregate import merge_events, _flip_spread
from scripts.platformkit.odds_provider.base import OddsEvent


def _espn_event():
    return OddsEvent(
        event_id="e1", sport="nba", home="Boston Celtics",
        away="Los Angeles Lakers", commence_time=None,
        prices={"espn:DK": {
            "home": 1.66, "away": 2.30,
            "spread": {"home": {"line": -5.5, "odds": 1.91},
                       "away": {"line": 5.5, "odds": 1.91}},
            "total": {"over": {"line": 220.5, "odds": 1.95},
                      "under": {"line": 220.5, "odds": 1.87}},
        }}, source="espn", as_of="2026-06-20T12:00:00+00:00")


def _pinnacle_event_flipped():
    # Same game, opposite orientation (Lakers listed as home).
    return OddsEvent(
        event_id="p1", sport="nba", home="Los Angeles Lakers",
        away="Boston Celtics", commence_time=None,
        prices={"pinnacle": {
            "home": 2.25, "away": 1.69,
            "spread": {"home": {"line": 5.5, "odds": 1.92},
                       "away": {"line": -5.5, "odds": 1.90}},
            "total": {"over": {"line": 221.0, "odds": 1.90},
                      "under": {"line": 221.0, "odds": 1.92}},
        }}, source="pinnacle", as_of="2026-06-20T12:00:00+00:00")


class TestFlipSpreadHelper:
    def test_legs_swap(self):
        node = {"home": {"line": 5.5, "odds": 1.92},
                "away": {"line": -5.5, "odds": 1.90}}
        out = _flip_spread(node)
        assert out["home"]["line"] == -5.5
        assert out["away"]["line"] == 5.5

    def test_non_dict_passthrough(self):
        assert _flip_spread(None) is None


class TestMergeCarriesAllMarkets:
    def _merged(self):
        merged = merge_events([[_espn_event()], [_pinnacle_event_flipped()]])
        assert len(merged) == 1, "same game should merge to one event"
        return merged[0]

    def test_both_venues_present(self):
        ev = self._merged()
        assert "espn:DK" in ev.prices
        assert "pinnacle" in ev.prices

    def test_pinnacle_moneyline_flipped(self):
        ev = self._merged()
        # Target orientation = Celtics home. Pinnacle had Celtics as away (1.69).
        assert abs(ev.prices["pinnacle"]["home"] - 1.69) < 1e-9
        assert abs(ev.prices["pinnacle"]["away"] - 2.25) < 1e-9

    def test_pinnacle_spread_carried_and_flipped(self):
        ev = self._merged()
        spread = ev.prices["pinnacle"].get("spread")
        assert spread is not None, "spread dropped on flip (regression)"
        # Celtics (now home) was the away leg on Pinnacle -> line -5.5.
        assert spread["home"]["line"] == -5.5
        assert spread["away"]["line"] == 5.5

    def test_pinnacle_total_carried(self):
        ev = self._merged()
        total = ev.prices["pinnacle"].get("total")
        assert total is not None, "total dropped on flip (regression)"
        assert total["over"]["line"] == 221.0
        assert total["under"]["line"] == 221.0
