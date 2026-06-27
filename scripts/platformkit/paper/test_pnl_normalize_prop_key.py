"""Regression test: distinct player props must NOT collapse into one bankroll position.

Bug (fixed 2026-06-24): _clv_market_key was (sport, matchup, line, day) with no prop
identity, so 50+ players' o/u-0.5 props in one game collapsed to a SINGLE position --
silently dropping ~90% of the prop book and overstating the bankroll. The key now carries
prop_player + prop_stat, so distinct props stay distinct and only a prop's own over/under
collapse.

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/paper/test_pnl_normalize_prop_key.py -q
"""
from __future__ import annotations

from scripts.platformkit.paper import pnl_normalize as nz


def _prop(player, stat, side, outcome, dec=1.9, line=0.5):
    return {"sport": "mlb", "matchup": "TEX @ MIA", "game_date": "2026-06-24",
            "market_type": "prop", "prop_player": player, "prop_stat": stat,
            "prop_side": side, "line": line, "taken_decimal": dec, "outcome": outcome,
            "model_prob": 0.6, "status": "settled", "channel": "paper",
            "unit_result": (dec - 1.0) if outcome == "win" else -1.0}


def test_distinct_props_are_distinct_positions():
    rows = [
        _prop("Player A", "Hits", "over", "loss"),
        _prop("Player B", "Hits", "over", "loss"),
        _prop("Player C", "Hits", "over", "loss"),
    ]  # three DIFFERENT players, same game/line/stat -> three markets, all kept
    sel = nz.select_clv_positions(rows)
    assert len(sel) == 3
    flat = nz.normalize_flat(sel)
    assert round(sum(r["unit_result"] for r in flat), 6) == -3.0  # all three losses count


def test_same_prop_over_and_under_collapse_to_one():
    rows = [
        _prop("Player A", "Hits", "over", "win", dec=2.0),   # backed side (higher model_prob)
        {**_prop("Player A", "Hits", "under", "loss"), "model_prob": 0.4},
    ]  # SAME prop, two sides -> ONE market (the model-backed side)
    sel = nz.select_clv_positions(rows)
    assert len(sel) == 1
    assert sel[0]["prop_side"] == "over"  # higher model_prob kept


def test_prop_key_carries_player_and_stat():
    a = nz._clv_market_key(_prop("Player A", "Hits", "over", "win"))
    b = nz._clv_market_key(_prop("Player B", "Hits", "over", "win"))
    c = nz._clv_market_key(_prop("Player A", "Runs", "over", "win"))
    assert a != b and a != c and b != c  # player and stat both discriminate


def test_moneyline_two_way_still_collapses():
    # a moneyline row has no prop fields -> key unchanged behavior (home+away = one market)
    home = {"sport": "mlb", "matchup": "TEX @ MIA", "game_date": "2026-06-24",
            "line": None, "side": "home", "model_prob": 0.55, "status": "settled",
            "outcome": "win", "taken_decimal": 1.9, "unit_result": 0.9}
    away = {**home, "side": "away", "model_prob": 0.45, "outcome": "loss",
            "unit_result": -1.0}
    assert nz._clv_market_key(home) == nz._clv_market_key(away)
    assert len(nz.select_clv_positions([home, away])) == 1
