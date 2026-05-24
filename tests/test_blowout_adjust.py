"""
test_blowout_adjust.py -- tests for cycle 88f blowout / garbage-time scaling.

Covers each rule branch in scripts/blowout_adjust.blowout_factor plus the
integration check that a 12-min starter projection drops into the expected
4-7 min band during a 25-pt Q4 blowout.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.blowout_adjust import (  # noqa: E402
    apply_to_projections,
    blowout_factor,
)


# ---------------------------------------------------------------------------
# Each rule branch -> expected factor
# ---------------------------------------------------------------------------

def test_pre_q4_close_game_returns_one_for_both():
    """Q1-Q3 or competitive Q4 (margin<15) -> 1.00 for both roles."""
    # Mid Q3, modest margin
    assert blowout_factor(8, 3, 5.0, True) == 1.00
    assert blowout_factor(8, 3, 5.0, False) == 1.00
    # Q4 but margin under 15
    assert blowout_factor(10, 4, 9.0, True) == 1.00
    assert blowout_factor(10, 4, 9.0, False) == 1.00


def test_q4_mild_lean_bucket_15_to_19():
    """Q4 margin 15-19 -> starters 0.85, bench 1.05."""
    assert blowout_factor(15, 4, 8.0, True) == 0.85
    assert blowout_factor(19, 4, 8.0, True) == 0.85
    assert blowout_factor(15, 4, 8.0, False) == 1.05
    assert blowout_factor(19, 4, 8.0, False) == 1.05


def test_q4_likely_blowout_bucket_20_to_29():
    """Q4 margin 20-29 -> starters 0.55, bench 1.30."""
    assert blowout_factor(20, 4, 8.0, True) == 0.55
    assert blowout_factor(29, 4, 8.0, True) == 0.55
    assert blowout_factor(20, 4, 8.0, False) == 1.30
    assert blowout_factor(29, 4, 8.0, False) == 1.30


def test_q4_garbage_time_bucket_30_plus():
    """Q4 margin 30+ -> starters 0.25, bench 1.50."""
    assert blowout_factor(30, 4, 8.0, True) == 0.25
    assert blowout_factor(45, 4, 8.0, True) == 0.25
    assert blowout_factor(30, 4, 8.0, False) == 1.50
    assert blowout_factor(45, 4, 8.0, False) == 1.50


def test_q4_full_on_blowout_last_3_min_margin_25_plus():
    """Q4 last 3:00 + margin > 25 -> starters 0.10, bench 1.60 (most extreme)."""
    # Boundary: 26 pts, exactly 3 min left
    assert blowout_factor(26, 4, 3.0, True) == 0.10
    assert blowout_factor(26, 4, 3.0, False) == 1.60
    # 35 pts with 1 min -- still extreme rule (shadows the 30+ rule)
    assert blowout_factor(35, 4, 1.0, True) == 0.10
    assert blowout_factor(35, 4, 1.0, False) == 1.60


def test_starter_factor_monotonic_decreasing_in_margin():
    """As Q4 margin grows, starter factor must never increase."""
    margins = [5, 14, 15, 19, 20, 29, 30, 45]
    factors = [blowout_factor(m, 4, 8.0, True) for m in margins]
    for a, b in zip(factors, factors[1:]):
        assert a >= b, f"starter factor jumped up: {factors}"


def test_bench_factor_monotonic_increasing_in_margin():
    """As Q4 margin grows, bench factor must never decrease."""
    margins = [5, 14, 15, 19, 20, 29, 30, 45]
    factors = [blowout_factor(m, 4, 8.0, False) for m in margins]
    for a, b in zip(factors, factors[1:]):
        assert a <= b, f"bench factor dropped: {factors}"


def test_end_of_q4_tight_game_returns_one():
    """Tight margin (5 pts, 30 sec left) -> 1.00 for both -- close game."""
    # 30 sec = 0.5 min remaining
    assert blowout_factor(5, 4, 0.5, True) == 1.00
    assert blowout_factor(5, 4, 0.5, False) == 1.00


def test_overtime_returns_one():
    """OT is by definition a one-possession game; no garbage time."""
    assert blowout_factor(2, 5, 4.0, True) == 1.00
    assert blowout_factor(2, 5, 4.0, False) == 1.00


def test_integration_12_min_projection_drops_to_4_to_7_for_starter_q4_25pt():
    """A 12-min starter projection in 25-pt Q4 blowout lands in 4-7 min band.

    25 pts at 5:00 left in Q4 -> margin 20-29 bucket -> starter factor 0.55.
    12 * 0.55 = 6.6, comfortably in the 4-7 band the spec calls for.
    """
    snap = {
        "game_id": "0022400999",
        "period": 4,
        "clock": "5:00",
        "home_score": 110,
        "away_score": 85,  # margin 25
        "players": [
            {"player_id": 1, "is_starter": True},
            {"player_id": 2, "is_starter": False},
        ],
    }
    projs = [
        {"player_id": 1, "name": "Star", "is_starter": True,
         "remaining_min": 12.0, "proj_pts": 24.0},
        {"player_id": 2, "name": "Bench", "is_starter": False,
         "remaining_min": 4.0,  "proj_pts": 4.0},
    ]
    adj = apply_to_projections(snap, projs)

    star = next(r for r in adj if r["player_id"] == 1)
    bench = next(r for r in adj if r["player_id"] == 2)

    assert star["blowout_factor"] == 0.55
    assert 4.0 <= star["remaining_min"] <= 7.0, star["remaining_min"]
    # Bench picks up minutes
    assert bench["blowout_factor"] == 1.30
    assert bench["remaining_min"] > 4.0


def test_apply_preserves_non_numeric_fields_and_adds_audit_factor():
    """Strings, ids, booleans pass through; blowout_factor key always added."""
    snap = {"period": 1, "clock": "11:30", "home_score": 8, "away_score": 6,
            "players": []}
    projs = [{"player_id": 99, "name": "Bench Guy", "is_starter": False,
              "proj_pts": 5.5, "proj_reb": 2.0}]
    adj = apply_to_projections(snap, projs)
    assert adj[0]["name"] == "Bench Guy"
    assert adj[0]["blowout_factor"] == 1.00
    # Pre-Q4 -> no scaling
    assert adj[0]["proj_pts"] == 5.5
    assert adj[0]["proj_reb"] == 2.0
