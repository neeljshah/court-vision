"""Per-file test for kalshi_pricers -- the player_prop + team_total Kalshi pricers.

Offline (injected board_lookup / rpg_lookup). Pins: title parsing, the K+ -> P(over K-0.5)
mapping, the run-rate Poisson totals projection, and the honest None-on-any-gap (so the
edge-finder skips rather than invents). No network.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_kalshi_pricers.py -q
"""
from __future__ import annotations

from scripts.platformkit.pm_trading import kalshi_pricers as K


# -- player_prop --------------------------------------------------------------

def test_parse_prop_title():
    assert K.parse_prop_title("Pete Crow-Armstrong: 1+ home runs") == (
        "Pete Crow-Armstrong", "Home Runs", 1)
    assert K.parse_prop_title("Aaron Judge: 2+ hits") == ("Aaron Judge", "Hits", 2)
    assert K.parse_prop_title("no colon here") is None
    assert K.parse_prop_title("Player X: nonsense stat") is None


def test_prop_pricer_maps_threshold_to_line():
    seen = {}

    def _board(player, stat, line):
        seen["call"] = (player, stat, line)
        return 0.18

    pricer = K.make_prop_pricer(_board)
    p = pricer({"title": "Pete Crow-Armstrong: 1+ home runs"})
    assert p == 0.18
    assert seen["call"] == ("Pete Crow-Armstrong", "Home Runs", 0.5)   # 1+ -> over 0.5


def test_prop_pricer_none_when_no_projection():
    pricer = K.make_prop_pricer(lambda p, s, l: None)
    assert pricer({"title": "Aaron Judge: 3+ hits"}) is None
    assert pricer({"title": "unparsable"}) is None


# -- team_total ---------------------------------------------------------------

def test_poisson_sf_basics():
    assert K._poisson_sf(0.0, 5) is None
    # high lambda vs low line -> near-certain over
    assert K._poisson_sf(10.0, 4) > 0.97
    # low lambda vs high line -> near-zero
    assert K._poisson_sf(4.0, 12) < 0.02


def test_parse_totals_market():
    m = {"title": "Philadelphia vs New York M Total Runs?",
         "ticker": "KXMLBTOTAL-26JUN261910PHINYM-9"}
    assert K.parse_totals_market(m) == ("Philadelphia", "New York M", 9.0)
    assert K.parse_totals_market({"title": "no versus here"}) is None


def test_totals_pricer_projects_and_prices():
    # both teams 5 RPG scored / 4 allowed -> proj = (5+4)/2 + (5+4)/2 = 9 runs
    rpg = {"Philadelphia": (5.0, 4.0), "New York M": (5.0, 4.0)}
    pricer = K.make_totals_pricer(lambda t: rpg.get(t))
    m = {"title": "Philadelphia vs New York M Total Runs?",
         "ticker": "KXMLBTOTAL-X-9"}
    p = pricer(m)
    assert p is not None and 0.0 < p < 1.0          # a real P(total >= 9)
    # unknown team -> honest None (skip), never invented
    assert pricer({"title": "Foo vs Bar Total Runs?", "ticker": "X-9"}) is None


def test_build_pricers_registry():
    reg = K.build_pricers(board_lookup=lambda p, s, l: 0.5,
                          rpg_lookup=lambda t: (5.0, 4.0))
    assert "player_prop" in reg and "team_total" in reg
    # without rpg_lookup, team_total is omitted (no totals model -> honest absence)
    reg2 = K.build_pricers(board_lookup=lambda p, s, l: 0.5)
    assert "team_total" not in reg2
