"""tests/test_foul_trouble_adjust.py — cycle 88e (loop 5).

Covers the pure factor heuristic + snapshot-level projection adjustment for
scripts/foul_trouble_adjust.py.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.foul_trouble_adjust import (
    adjust_snapshot,
    apply_factor_to_projection,
    clock_str_to_minutes,
    foul_trouble_factor,
)


# ─── Rule-branch coverage ───────────────────────────────────────────────────

def test_five_plus_fouls_anywhere_returns_0_40():
    # Any period, any clock — deep trouble.
    assert foul_trouble_factor(5, 1, 10.0) == 0.40
    assert foul_trouble_factor(5, 2, 5.0) == 0.40
    assert foul_trouble_factor(5, 3, 11.0) == 0.40
    assert foul_trouble_factor(5, 4, 0.5) == 0.40
    assert foul_trouble_factor(6, 4, 0.0) == 0.40


def test_four_fouls_in_q3_returns_0_55():
    assert foul_trouble_factor(4, 3, 11.5) == 0.55
    assert foul_trouble_factor(4, 3, 0.1) == 0.55


def test_four_fouls_early_q4_returns_0_65():
    # >6 minutes left in Q4 -> medium leash.
    assert foul_trouble_factor(4, 4, 11.0) == 0.65
    assert foul_trouble_factor(4, 4, 6.01) == 0.65


def test_four_fouls_late_q4_returns_0_90():
    # <=6 minutes in Q4 -> coach lets him play.
    assert foul_trouble_factor(4, 4, 6.0) == 0.90
    assert foul_trouble_factor(4, 4, 1.0) == 0.90
    # Any OT period also falls through to the must-win 0.90 branch.
    assert foul_trouble_factor(4, 5, 5.0) == 0.90


def test_three_fouls_in_q2_returns_0_80():
    assert foul_trouble_factor(3, 2, 11.0) == 0.80
    assert foul_trouble_factor(3, 2, 0.1) == 0.80
    # 3 fouls anywhere ELSE is fine.
    assert foul_trouble_factor(3, 1, 5.0) == 1.00
    assert foul_trouble_factor(3, 3, 5.0) == 1.00
    assert foul_trouble_factor(3, 4, 5.0) == 1.00


def test_baseline_no_trouble_returns_1_0():
    # Common safe states.
    for pf in (0, 1, 2):
        for period in (1, 2, 3, 4):
            assert foul_trouble_factor(pf, period, 10.0) == 1.0


# ─── Invariants ─────────────────────────────────────────────────────────────

def test_factor_never_exceeds_one():
    # Sweep every plausible (pf, period, clock) combo — factor must be <= 1.0.
    for pf in range(0, 7):
        for period in range(1, 6):
            for clock in (11.5, 6.5, 6.0, 3.0, 0.1):
                f = foul_trouble_factor(pf, period, clock)
                assert 0.0 <= f <= 1.0, (pf, period, clock, f)


def test_factor_monotonic_in_fouls():
    # At a fixed (period, clock), more fouls must never give a HIGHER factor
    # than fewer fouls. (Equality is fine — multiple low-pf states all map
    # to 1.0.)
    for period in (1, 2, 3, 4, 5):
        for clock in (11.0, 7.0, 6.0, 3.0):
            prev = 1.0001  # strictly greater than any valid factor
            for pf in range(0, 7):
                cur = foul_trouble_factor(pf, period, clock)
                assert cur <= prev + 1e-9, (
                    f"non-monotonic at period={period} clock={clock} "
                    f"pf={pf}: {prev:.3f} -> {cur:.3f}")
                prev = cur


# ─── Integration: factor applied to a remaining-minutes projection ──────────

def test_factor_halves_20min_projection_in_deep_trouble():
    # 20 min remaining baseline. 5+ fouls -> 0.40 factor -> 8 min adjusted.
    proj = {"min": 20.0, "pts": 12.0, "reb": 4.0, "ast": 3.0}
    f = foul_trouble_factor(5, 3, 8.0)
    adj = apply_factor_to_projection(proj, f)
    assert adj["min"] == pytest.approx(8.0, abs=0.01)
    # 8 minutes is within the "halves to ~8-12 min" target band.
    assert 8.0 <= adj["min"] <= 12.0 or adj["min"] == pytest.approx(8.0)
    # Counts must scale proportionally (linear in floor time).
    assert adj["pts"] == pytest.approx(12.0 * 0.40, abs=0.01)
    assert adj["reb"] == pytest.approx(4.0 * 0.40, abs=0.01)
    assert adj["ast"] == pytest.approx(3.0 * 0.40, abs=0.01)
    # Audit field present.
    assert adj["foul_trouble_factor"] == 0.40


def test_factor_lands_in_8_to_12_min_band_for_q3_four_fouls():
    # 4 fouls in Q3 with 20 min remaining -> factor 0.55 -> 11.0 min.
    # Squarely inside the spec's "~8-12 min" target band.
    proj = {"min": 20.0, "pts": 18.0}
    f = foul_trouble_factor(4, 3, 5.0)
    adj = apply_factor_to_projection(proj, f)
    assert 8.0 <= adj["min"] <= 12.0


def test_apply_factor_passes_through_unknown_stats():
    # Rate / percentage stats are NOT minute-linear and must be untouched.
    proj = {"pts": 10.0, "ts_pct": 0.55, "usage": 0.28}
    adj = apply_factor_to_projection(proj, 0.55)
    assert adj["pts"] == pytest.approx(5.5, abs=0.01)
    assert adj["ts_pct"] == 0.55
    assert adj["usage"] == 0.28


# ─── Snapshot-level glue ────────────────────────────────────────────────────

def test_adjust_snapshot_marks_trouble_per_player():
    snapshot = {
        "game_id": "0022400001",
        "period": 3,
        "clock": "5:30",
        "players": [
            {"player_id": 1, "name": "Star",     "team": "LAL", "pf": 4},
            {"player_id": 2, "name": "Bench",    "team": "LAL", "pf": 2},
            {"player_id": 3, "name": "FouledOut","team": "DEN", "pf": 5},
        ],
    }
    rows = adjust_snapshot(snapshot)
    by_id = {r["player_id"]: r for r in rows}
    assert by_id[1]["factor"] == 0.55  # 4 in Q3
    assert by_id[2]["factor"] == 1.00  # safe
    assert by_id[3]["factor"] == 0.40  # 5+
    # clock parsed correctly.
    for r in rows:
        assert r["clock_min"] == pytest.approx(5.5, abs=0.01)


def test_adjust_snapshot_applies_projection_when_provided():
    snapshot = {
        "game_id": "0022400002",
        "period": 4,
        "clock": "8:00",
        "players": [
            {"player_id": 10, "name": "EarlyQ4", "team": "BOS", "pf": 4},
        ],
    }
    projections = {10: {"min": 12.0, "pts": 8.0, "reb": 3.0}}
    rows = adjust_snapshot(snapshot, projections)
    assert len(rows) == 1
    r = rows[0]
    assert r["factor"] == 0.65  # 4 fouls, Q4, >6 min left
    assert r["projection"]["pts"] == 8.0
    assert r["adjusted_projection"]["pts"] == pytest.approx(8.0 * 0.65, abs=0.01)
    assert r["adjusted_projection"]["min"] == pytest.approx(12.0 * 0.65, abs=0.01)


def test_clock_str_to_minutes_defaults_safely():
    assert clock_str_to_minutes("5:30") == pytest.approx(5.5, abs=0.01)
    assert clock_str_to_minutes("0:00") == 0.0
    assert clock_str_to_minutes("11:59") == pytest.approx(11.0 + 59/60, abs=0.01)
    # Empty / junk -> full period (safe pre-tip default).
    assert clock_str_to_minutes("") == 12.0
    assert clock_str_to_minutes("garbage") == 12.0
