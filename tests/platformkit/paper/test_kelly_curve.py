"""Per-file test for the capped quarter-Kelly bankroll overlay.

Honest contract:
  (1) edge-proportional: a higher-conviction (bigger model-vs-price edge) bet stakes MORE
      Kelly units than a thin-edge bet; a non-positive-edge bet stakes 0.
  (2) RECONCILES: the Kelly curve is the literal sum of stake_i * per-unit-result_i.
  (3) UNITS only -- there is NO $/ROI field anywhere in the overlay payload.
"""
from __future__ import annotations

from scripts.platformkit.paper import kelly_curve as K


def _bet(model_prob, taken_decimal, unit_result, day="2026-06-20"):
    return {"model_prob": model_prob, "taken_decimal": taken_decimal,
            "unit_result": unit_result, "settled_at": f"{day}T12:00:00Z"}


def test_overlay_is_edge_proportional_and_units_only():
    # strong edge (model 0.62 vs implied ~0.50) should stake MORE than a thin edge.
    strong = K._kelly_stake(_bet(0.62, 2.00, 1.0))
    thin = K._kelly_stake(_bet(0.52, 2.00, 1.0))
    assert strong > thin >= 0.0
    # a non-positive edge (model below the implied price) stakes nothing
    assert K._kelly_stake(_bet(0.40, 2.00, -1.0)) == 0.0
    # missing edge inputs fall back to the flat 1.0 unit (curve still reconciles)
    assert K._kelly_stake({"unit_result": 1.0}) == 1.0


def test_overlay_reconciles_and_has_no_dollar_field():
    bets = [_bet(0.62, 2.00, 1.0), _bet(0.40, 2.00, -1.0), _bet(0.55, 2.20, -1.0)]
    ov = K.kelly_overlay(bets, start_units=100.0)
    # net == sum of stake_i * unit_result_i (literal reconciliation)
    expect = sum(K._kelly_stake(b) * float(b["unit_result"]) for b in bets)
    assert abs(ov["kelly_net_units"] - round(expect, 6)) < 1e-6
    assert abs(ov["kelly_current_units"] - (100.0 + ov["kelly_net_units"])) < 1e-6
    assert ov["kelly_reconciles"] is True and ov["kelly_capped"] is True
    # UNITS only -- no dollar/roi token anywhere
    blob = str(ov).lower()
    assert "$" not in blob and "roi" not in blob and "dollar" not in blob


def test_empty_is_flat_start():
    ov = K.kelly_overlay([], start_units=100.0)
    assert ov["kelly_current_units"] == 100.0 and ov["kelly_net_units"] == 0.0
    assert ov["kelly_n_sized"] == 0
