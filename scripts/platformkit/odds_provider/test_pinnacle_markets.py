"""Per-file tests for Pinnacle spread + total parsing (markets completeness).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_pinnacle_markets.py -q

Acceptance:
  - A period=0 spread market -> sides['spread'] with home/away line+odds.
  - A period=0 total market  -> sides['total'] with over/under line+odds.
  - Moneyline still parses unchanged alongside spread/total.
  - A partial spread (one leg missing a price) is dropped (never fabricated).
  - Non-zero period spread/total markets are ignored (full-game only).
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.pinnacle import (
    parse_games, _spread_node, _total_node,
)

_MATCHUPS = [
    {"id": 1, "parentId": None, "type": "matchup",
     "startTime": "2026-06-20T23:00:00Z",
     "participants": [
         {"alignment": "home", "name": "Boston Celtics"},
         {"alignment": "away", "name": "Los Angeles Lakers"},
     ]},
]


def _ml(period=0):
    return {"type": "moneyline", "period": period, "matchupId": 1,
            "prices": [{"designation": "home", "price": -150},
                       {"designation": "away", "price": 130}]}


def _spread(period=0):
    return {"type": "spread", "period": period, "matchupId": 1,
            "prices": [{"designation": "home", "points": -5.5, "price": -110},
                       {"designation": "away", "points": 5.5, "price": -110}]}


def _total(period=0):
    return {"type": "total", "period": period, "matchupId": 1,
            "prices": [{"points": 220.5, "price": -108},
                       {"points": 220.5, "price": -112}]}


def _venue(events):
    assert len(events) == 1
    return events[0].prices.get("pinnacle", {})


class TestSpreadParse:
    def test_spread_node_present(self):
        sides = _venue(parse_games(_MATCHUPS, [_spread()], "nba"))
        assert "spread" in sides
        assert sides["spread"]["home"]["line"] == -5.5
        assert sides["spread"]["away"]["line"] == 5.5
        assert sides["spread"]["home"]["odds"] > 1.0
        assert sides["spread"]["away"]["odds"] > 1.0

    def test_partial_spread_dropped(self):
        bad = {"type": "spread", "period": 0, "matchupId": 1,
               "prices": [{"designation": "home", "points": -5.5, "price": -110},
                          {"designation": "away", "points": 5.5}]}  # no price
        assert _spread_node(bad["prices"]) is None

    def test_nonzero_period_ignored(self):
        sides = _venue(parse_games(_MATCHUPS, [_spread(period=1)], "nba"))
        assert "spread" not in sides


class TestTotalParse:
    def test_total_node_present(self):
        sides = _venue(parse_games(_MATCHUPS, [_total()], "nba"))
        assert "total" in sides
        assert sides["total"]["over"]["line"] == 220.5
        assert sides["total"]["under"]["line"] == 220.5
        assert sides["total"]["over"]["odds"] > 1.0

    def test_index_order_over_under(self):
        node = _total_node([{"points": 200.5, "price": -110},
                            {"points": 200.5, "price": -110}])
        assert "over" in node and "under" in node

    def test_partial_total_dropped(self):
        assert _total_node([{"points": 220.5, "price": -110}]) is None


class TestAllThreeMarkets:
    def test_moneyline_spread_total_together(self):
        sides = _venue(parse_games(
            _MATCHUPS, [_ml(), _spread(), _total()], "nba"))
        assert "home" in sides and "away" in sides  # moneyline
        assert "spread" in sides
        assert "total" in sides

    def test_moneyline_only_still_works(self):
        sides = _venue(parse_games(_MATCHUPS, [_ml()], "nba"))
        assert sides.get("home") and sides.get("away")
        assert "spread" not in sides and "total" not in sides
