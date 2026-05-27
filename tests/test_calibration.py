"""tests/test_calibration.py — guard the filter calibration grid search.

Three tests:
1. grid_floor_per_quarter produces expected shape over a synthetic settled CSV.
2. recommend_floor prefers high-ROI subject to N>=100.
3. decision_engine patched constants load without exception (smoke import test).
"""
from __future__ import annotations

import io
import math
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pandas as pd

from scripts.calibrate_filters import (
    FLOOR_GRID,
    MIN_N,
    SNAP_LABELS,
    grid_floor_per_quarter,
    recommend_floor,
    load_settled_csvs,
)


# ── synthetic data factory ─────────────────────────────────────────────────────

def _make_settled_csv(path: str, *, n_per_cell: int = 150) -> None:
    """Write a minimal settled CSV with synthetic rows.

    Creates n_per_cell rows per (period × tier) combination so that every
    cell has enough rows to meet MIN_N. EV and realized returns are chosen so
    that higher EV → higher ROI, allowing the floor recommendation to fire.
    """
    rows = []
    # period "2"=endQ1, "3"=endQ2, "4"=endQ3
    for period in ["2", "3", "4"]:
        # Low-EV rows (Tier C, EV = -0.4 → bad ROI)
        for i in range(n_per_cell):
            rows.append({
                "ts": "2026-05-27T00:00:00",
                "game_id": "G001",
                "period": period,
                "clock_remaining": "300",
                "player_id": f"p{i}",
                "name": f"Player{i}",
                "team": "BOS",
                "stat": "pts",
                "side": "over",
                "line": "20.5",
                "book": "l5_proxy",
                "odds": "-110",
                "model_proj": "10.0",
                "current_stat": "0",
                "sigma": "5.0",
                "raw_ev": "-0.40",    # Tier C
                "kelly": "0.0",
                "tier": "C",
                "gate_status": "passed",
                "gate_blocked_by": "",
                "source": "snapshot_replay",
                "actual_stat": "18.0",
                "outcome": "miss",
                "realized_return_$1": "-1.0",
                "settled_at": "2026-05-27T06:00:00+00:00",
            })
        # High-EV rows (Tier A, EV = 0.20 → good ROI)
        for i in range(n_per_cell):
            rows.append({
                "ts": "2026-05-27T00:00:00",
                "game_id": "G001",
                "period": period,
                "clock_remaining": "300",
                "player_id": f"q{i}",
                "name": f"Star{i}",
                "team": "LAL",
                "stat": "pts",
                "side": "over",
                "line": "20.5",
                "book": "l5_proxy",
                "odds": "-110",
                "model_proj": "28.0",
                "current_stat": "10",
                "sigma": "5.0",
                "raw_ev": "0.20",    # Tier A
                "kelly": "0.15",
                "tier": "A",
                "gate_status": "passed",
                "gate_blocked_by": "",
                "source": "snapshot_replay",
                "actual_stat": "30.0",
                "outcome": "hit",
                "realized_return_$1": "0.9091",
                "settled_at": "2026-05-27T06:00:00+00:00",
            })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


# ── test 1: shape ──────────────────────────────────────────────────────────────

def test_grid_floor_produces_expected_shape():
    """grid_floor_per_quarter must return a dict with 3 snaps × len(FLOOR_GRID) cells."""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as fh:
        path = fh.name
    try:
        _make_settled_csv(path, n_per_cell=200)
        df = load_settled_csvs(path)
        passed = df[df["gate_status"] == "passed"].copy()
        result = grid_floor_per_quarter(passed)
        # Must have exactly 3 snapshot keys
        assert set(result.keys()) == {"endQ1", "endQ2", "endQ3"}, result.keys()
        # Each snapshot must have an entry for every floor in the grid
        for snap, cells in result.items():
            assert set(cells.keys()) == set(FLOOR_GRID), (
                f"{snap}: expected floors {FLOOR_GRID}, got {list(cells.keys())}"
            )
            # Each cell returns a 4-tuple (n, hit_rate, roi_flat, roi_kelly)
            for floor, val in cells.items():
                assert len(val) == 4, f"{snap}[{floor}]: expected 4-tuple, got {val}"
                n, hr, roi_flat, roi_kelly = val
                assert isinstance(n, int), f"n should be int, got {type(n)}"
    finally:
        os.unlink(path)


# ── test 2: recommendation prefers high-ROI ────────────────────────────────────

def test_recommend_floor_prefers_high_roi():
    """recommend_floor must pick the floor with highest ROI subject to N>=MIN_N.

    In our synthetic CSV: high-EV rows have ROI=+0.91 and low-EV rows have
    ROI=-1.00. Once the floor rises above 0.20 (=high EV threshold), all
    remaining rows are winners. The recommendation should pick a floor that
    excludes the low-EV rows.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as fh:
        path = fh.name
    try:
        _make_settled_csv(path, n_per_cell=200)
        df = load_settled_csvs(path)
        passed = df[df["gate_status"] == "passed"].copy()
        result = grid_floor_per_quarter(passed)
        rec = recommend_floor(result)
        # The recommended floor must be at least 0.04 (since low-EV rows hurt ROI)
        for snap, floor in rec.items():
            n_at_floor = result[snap][floor][0]
            assert n_at_floor >= MIN_N, (
                f"{snap}: recommended floor {floor} has n={n_at_floor} < MIN_N={MIN_N}"
            )
            # ROI at recommended floor should beat ROI at floor=0.01
            roi_rec = result[snap][floor][2]
            roi_baseline = result[snap][0.01][2]
            assert roi_rec >= roi_baseline - 1e-9, (
                f"{snap}: recommended ROI {roi_rec:.4f} < baseline {roi_baseline:.4f}"
            )
    finally:
        os.unlink(path)


# ── test 3: decision_engine loads cleanly ──────────────────────────────────────

def test_decision_engine_smoke_import():
    """Importing decision_engine and instantiating DecisionEngine must not raise."""
    from src.prediction.decision_engine import (
        DecisionEngine,
        TIER_B_EV,
        TIER_A_EV,
        TIER_S_EV,
        _EMIT_FLOOR_BY_PERIOD,
        _EV_CEILING_BY_PERIOD,
        classify_tier,
    )
    # Patched constants sanity checks
    assert TIER_B_EV == 0.04, f"Expected TIER_B_EV=0.04, got {TIER_B_EV}"
    assert TIER_A_EV == 0.04, f"Expected TIER_A_EV=0.04, got {TIER_A_EV}"
    assert TIER_S_EV == 0.08, f"Expected TIER_S_EV=0.08, got {TIER_S_EV}"

    # Per-period floors must be present for all 3 snapshot periods
    for period_str in ("2", "3", "4"):
        assert period_str in _EMIT_FLOOR_BY_PERIOD, (
            f"_EMIT_FLOOR_BY_PERIOD missing key '{period_str}'"
        )
        floor = _EMIT_FLOOR_BY_PERIOD[period_str]
        assert 0.0 < floor <= 1.0, f"floor for period {period_str} out of range: {floor}"

    # Per-period ceilings must be present
    for period_str in ("2", "3", "4"):
        assert period_str in _EV_CEILING_BY_PERIOD, (
            f"_EV_CEILING_BY_PERIOD missing key '{period_str}'"
        )
        ceil_ev = _EV_CEILING_BY_PERIOD[period_str]
        assert 0.0 < ceil_ev <= 1.0, f"ceiling for period {period_str} out of range: {ceil_ev}"

    # Q3 ceiling must be higher than Q1/Q2 (calibration rationale)
    assert _EV_CEILING_BY_PERIOD["4"] > _EV_CEILING_BY_PERIOD["2"], (
        "Q3 ceiling should be raised above Q1 ceiling (late-game edges are legitimate)"
    )

    # Engine must instantiate without error
    eng = DecisionEngine(emit_floor_ev=0.04)
    assert eng is not None

    # classify_tier must still work correctly with new TIER_B_EV
    assert classify_tier(0.09, 1.5) == "S"
    assert classify_tier(0.05, 0.0) == "A"
    assert classify_tier(0.04, 0.0) == "A"   # boundary: A exactly at TIER_A_EV
    assert classify_tier(0.02, 0.0) == "C"   # below TIER_B_EV=0.04 → C
    assert classify_tier(-0.10, 0.0) == "C"
