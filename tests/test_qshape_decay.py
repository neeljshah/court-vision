"""tests/test_qshape_decay.py — W-015 CV_QSHAPE_DECAY quarter-shape decay multiplier.

Tests:
  1. Flag OFF: project_snapshot output byte-identical to baseline (no change).
  2. Flag ON:  qshape_pace_factor returns values < 1.0 for AST/FG3M at endQ3.
  3. Flag ON:  blk/tov/stl stats are unchanged (excluded from shape adjustment).
  4. Flag ON:  endQ4 factor = 1.0 (no remaining quarters → no-op).
  5. Flag ON:  project_snapshot produces lower projections for AST at endQ3.
  6. Byte-identical check: flag OFF produces exact same float as pre-flag baseline.
  7. Clamping: factor stays in [0.80, 1.20] for all stats/periods.
  8. qshape_pace_factor at endQ1: remaining = Q2,Q3,Q4; factor < 1.0 for AST.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _snap(period: int, clock: str, pts: float = 18.0, reb: float = 6.0,
          ast: float = 5.0, fg3m: float = 2.0, blk: float = 1.0, tov: float = 2.0):
    """Build a minimal single-player snapshot."""
    return {
        "period": period,
        "clock": clock,
        "home_team": "OKC", "away_team": "NYK",
        "home_score": 50, "away_score": 45,
        "players": [{
            "player_id": 12345, "name": "Test Player", "team": "OKC",
            "min": 18.0,
            "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m,
            "stl": 1.0, "blk": blk, "tov": tov, "pf": 1,
        }],
    }


def _proj_by_stat(snap):
    """Run project_snapshot and return {stat: projected_final}."""
    return {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}


# ── 1. Flag OFF: byte-identical baseline ──────────────────────────────────────

def test_flag_off_byte_identical_endq3():
    """With CV_QSHAPE_DECAY=OFF, every stat is unchanged from pre-flag baseline."""
    old_flag = pig._CV_QSHAPE_DECAY
    snap = _snap(3, "00:00")  # endQ3
    try:
        pig._CV_QSHAPE_DECAY = False
        result_off = _proj_by_stat(snap)
        # Re-compute manually: at endQ3 (3/4 played), remaining = 1/3 of current
        # projected = current + current*(0.25/0.75) = current * 4/3
        for stat in pig.STATS:
            expected_endq3 = snap["players"][0][stat] * (4.0 / 3.0)
            assert result_off[stat] == pytest.approx(expected_endq3, abs=1e-4), (
                f"stat={stat} flag-OFF endQ3 should be current*4/3, got {result_off[stat]}")
    finally:
        pig._CV_QSHAPE_DECAY = old_flag


def test_flag_off_matches_flag_on_for_excluded_stats():
    """BLK/TOV/STL must be byte-identical whether flag is ON or OFF."""
    old_flag = pig._CV_QSHAPE_DECAY
    snap = _snap(3, "00:00")
    try:
        pig._CV_QSHAPE_DECAY = False
        off = _proj_by_stat(snap)
        pig._CV_QSHAPE_DECAY = True
        on_ = _proj_by_stat(snap)
        for stat in ("blk", "tov", "stl"):
            assert off[stat] == pytest.approx(on_[stat], abs=1e-9), (
                f"excluded stat={stat} must be byte-identical ON vs OFF")
    finally:
        pig._CV_QSHAPE_DECAY = old_flag


# ── 2. qshape_pace_factor values ─────────────────────────────────────────────

def test_qshape_factor_endq3_ast_less_than_one():
    """AST endQ3: remaining={Q4} rate < elapsed={Q1,Q2,Q3} mean rate => factor<1."""
    f = pig.qshape_pace_factor("ast", 3, 0.0)
    assert f < 1.0, f"AST endQ3 factor should be < 1.0, got {f}"
    # Verify it is in the expected neighborhood (0.85-0.92)
    assert 0.85 <= f <= 0.92, (
        f"AST endQ3 factor should be in [0.85, 0.92], got {f:.4f}")


def test_qshape_factor_endq3_fg3m_less_than_one():
    """FG3M endQ3: Q4 rate < Q1-Q3 mean => factor < 1.0."""
    f = pig.qshape_pace_factor("fg3m", 3, 0.0)
    assert f < 1.0, f"FG3M endQ3 factor should be < 1.0, got {f}"
    # In the range [0.86, 0.93]
    assert 0.86 <= f <= 0.93, (
        f"FG3M endQ3 factor should be in [0.86, 0.93], got {f:.4f}")


def test_qshape_factor_excluded_returns_one():
    """BLK/TOV/STL return 1.0 regardless of period (not in target set)."""
    for stat in ("blk", "tov", "stl"):
        for period in (1, 2, 3, 4):
            f = pig.qshape_pace_factor(stat, period, 0.0)
            assert f == pytest.approx(1.0), (
                f"qshape_pace_factor({stat!r}, {period}, 0) should be 1.0, got {f}")


def test_qshape_factor_endq4_returns_one():
    """At endQ4 (no remaining quarters) factor must be 1.0 for all stats."""
    for stat in ("pts", "reb", "ast", "fg3m"):
        f = pig.qshape_pace_factor(stat, 4, 0.0)
        assert f == pytest.approx(1.0), (
            f"qshape_pace_factor({stat!r}, 4, 0) should be 1.0 (no remaining qs), got {f}")


def test_qshape_factor_clamped_in_range():
    """Factor must be in [0.80, 1.20] for all target stats and periods."""
    for stat in ("pts", "reb", "ast", "fg3m"):
        for period in (1, 2, 3, 4):
            f = pig.qshape_pace_factor(stat, period, 0.0)
            assert 0.80 <= f <= 1.20, (
                f"qshape_pace_factor({stat!r}, {period}) = {f} outside [0.80,1.20]")


def test_qshape_factor_endq1_ast():
    """AST endQ1: remaining={Q2,Q3,Q4} vs elapsed={Q1} — mean decline expected."""
    f = pig.qshape_pace_factor("ast", 1, 0.0)
    # Q1 rate > avg(Q2,Q3,Q4) for AST so factor < 1.0
    assert f < 1.0, f"AST endQ1 factor should be < 1.0 (Q4 decline dominates), got {f}"


# ── 3. Flag ON changes target stats, leaves excluded stats unchanged ──────────

def test_flag_on_reduces_ast_endq3():
    """With flag ON at endQ3, AST projection decreases (shape factor < 1.0)."""
    old_flag = pig._CV_QSHAPE_DECAY
    snap = _snap(3, "00:00")
    try:
        pig._CV_QSHAPE_DECAY = False
        off = _proj_by_stat(snap)
        pig._CV_QSHAPE_DECAY = True
        on_ = _proj_by_stat(snap)
        assert on_["ast"] < off["ast"], (
            f"AST endQ3: flag ON ({on_['ast']:.4f}) should be < flag OFF ({off['ast']:.4f})")
        assert on_["fg3m"] < off["fg3m"], (
            f"FG3M endQ3: flag ON ({on_['fg3m']:.4f}) should be < flag OFF ({off['fg3m']:.4f})")
        # Excluded stats unchanged
        for stat in ("blk", "tov", "stl"):
            assert on_[stat] == pytest.approx(off[stat], abs=1e-9), (
                f"Excluded stat {stat} should not change")
    finally:
        pig._CV_QSHAPE_DECAY = old_flag


def test_flag_on_pts_reb_also_slightly_reduced_endq3():
    """PTS and REB also have shape factors < 1.0 at endQ3 (modest decline)."""
    old_flag = pig._CV_QSHAPE_DECAY
    snap = _snap(3, "00:00")
    try:
        pig._CV_QSHAPE_DECAY = False
        off = _proj_by_stat(snap)
        pig._CV_QSHAPE_DECAY = True
        on_ = _proj_by_stat(snap)
        assert on_["pts"] < off["pts"], "PTS endQ3: flag ON should be < OFF"
        assert on_["reb"] < off["reb"], "REB endQ3: flag ON should be < OFF"
    finally:
        pig._CV_QSHAPE_DECAY = old_flag


def test_flag_on_byte_identical_endq4():
    """At endQ4 (period=4, clock=0) both flags produce identical output
    because there is no remaining time (project_remaining=0 regardless of factor)."""
    old_flag = pig._CV_QSHAPE_DECAY
    snap = _snap(4, "00:00")
    try:
        pig._CV_QSHAPE_DECAY = False
        off = _proj_by_stat(snap)
        pig._CV_QSHAPE_DECAY = True
        on_ = _proj_by_stat(snap)
        for stat in pig.STATS:
            assert off[stat] == pytest.approx(on_[stat], abs=1e-9), (
                f"endQ4 stat={stat}: ON ({on_[stat]}) != OFF ({off[stat]})")
    finally:
        pig._CV_QSHAPE_DECAY = old_flag


# ── 4. Arithmetic spot check ──────────────────────────────────────────────────

def test_qshape_factor_ast_endq3_arithmetic():
    """Manually verify AST endQ3 factor from the module's rate table.

    elapsed = {Q1,Q2,Q3}: uses the exact constants in _QSHAPE_RATES (p=3 => range(1,4))
    remaining = {Q4}: range(4,5) from the table
    factor = mean_remaining / mean_elapsed
    """
    rates = pig._QSHAPE_RATES["ast"]
    # elapsed = range(1, p+1) = range(1, 4) = [1,2,3]
    elapsed_mean = sum(rates[q] for q in (1, 2, 3)) / 3.0
    # remaining = range(p+1, 5) = range(4, 5) = [4]
    remaining_mean = rates[4]
    expected = remaining_mean / elapsed_mean
    f = pig.qshape_pace_factor("ast", 3, 0.0)
    assert f == pytest.approx(expected, abs=1e-6), (
        f"AST endQ3: expected {expected:.4f}, got {f:.4f}")


def test_qshape_factor_pts_endq2_arithmetic():
    """Manually verify PTS endQ2 factor using the module's rate table.

    elapsed = {Q1,Q2}: range(1, 3) = [1,2]
    remaining = {Q3,Q4}: range(3, 5) = [3,4]
    factor = mean_remaining / mean_elapsed
    """
    rates = pig._QSHAPE_RATES["pts"]
    # elapsed = range(1, p+1) = range(1, 3) = [1,2]
    elapsed_mean = sum(rates[q] for q in (1, 2)) / 2.0
    # remaining = range(p+1, 5) = range(3, 5) = [3,4]
    remaining_mean = sum(rates[q] for q in (3, 4)) / 2.0
    expected = remaining_mean / elapsed_mean
    f = pig.qshape_pace_factor("pts", 2, 0.0)
    assert f == pytest.approx(expected, abs=1e-6), (
        f"PTS endQ2: expected {expected:.4f}, got {f:.4f}")
