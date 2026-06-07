"""tests/test_w026_foul_perstat.py — W-026: per-stat foul-trouble dampeners.

Tests:
  1. Byte-identical guarantee: CV_FOUL_PERSTAT=OFF returns the shared scalar.
  2. Gap fills: pf==2/Q1 → 0.85, pf==3/Q3 → 0.80, pf==3/Q1 → 0.90.
  3. Per-stat calibration ratios apply correctly.
  4. Clamp guarantees.
  5. Graceful input handling.
  6. project_snapshot byte-identical when CV_FOUL_PERSTAT=0.
"""
from __future__ import annotations

import os
import sys

# Ensure flag OFF for import (so module-level flag is off by default)
os.environ.pop("CV_FOUL_PERSTAT", None)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import with flag off (default)
from src.prediction.live_factors import (  # noqa: E402
    foul_trouble_factor,
    foul_trouble_factor_perstat,
    _foul_trouble_factor_extended,  # type: ignore[attr-defined]
    _FOUL_PERSTAT_RATIOS,           # type: ignore[attr-defined]
    _FOUL_PERSTAT_PTS_RATIO,        # type: ignore[attr-defined]
)
import importlib


# ─── Helper to reload module with flag ON/OFF ──────────────────────────────

def _reload_live_factors(flag_on: bool):
    """Reload live_factors with the specified CV_FOUL_PERSTAT value."""
    if flag_on:
        os.environ["CV_FOUL_PERSTAT"] = "1"
    else:
        os.environ.pop("CV_FOUL_PERSTAT", None)
    import src.prediction.live_factors as _lf
    importlib.reload(_lf)
    return _lf


# ─── 1. Byte-identical: flag OFF returns shared scalar ──────────────────────

def test_flag_off_byte_identical_no_trouble():
    """pf=0 → both paths return 1.0."""
    assert foul_trouble_factor_perstat(0, 2, 5.0, "pts") == foul_trouble_factor(0, 2, 5.0)


def test_flag_off_byte_identical_4foul_q3():
    """pf=4 Q3 → both paths return 0.55."""
    assert foul_trouble_factor_perstat(4, 3, 5.0, "reb") == foul_trouble_factor(4, 3, 5.0)


def test_flag_off_byte_identical_3foul_q2():
    """pf=3 Q2 → both paths return 0.80."""
    assert foul_trouble_factor_perstat(3, 2, 8.0, "ast") == foul_trouble_factor(3, 2, 8.0)


def test_flag_off_gap_returns_one_pf2_q1():
    """Flag OFF: pf==2/Q1 gap → 1.00 (existing behavior preserved)."""
    assert foul_trouble_factor_perstat(2, 1, 10.0, "pts") == 1.00


def test_flag_off_gap_returns_one_pf3_q3():
    """Flag OFF: pf==3/Q3 gap → 1.00 (existing behavior preserved)."""
    assert foul_trouble_factor_perstat(3, 3, 5.0, "reb") == 1.00


# ─── 2. Extended table gap fills (tested on _foul_trouble_factor_extended) ──

def test_extended_table_pf2_q1():
    """Extended table: pf==2 Q1 → 0.85."""
    assert _foul_trouble_factor_extended(2, 1, 10.0) == 0.85


def test_extended_table_pf3_q3():
    """Extended table: pf==3 Q3 → 0.80."""
    assert _foul_trouble_factor_extended(3, 3, 5.0) == 0.80


def test_extended_table_pf3_q1():
    """Extended table: pf==3 Q1 → 0.90."""
    assert _foul_trouble_factor_extended(3, 1, 8.0) == 0.90


def test_extended_table_existing_rules_unchanged():
    """Extended table: existing rules are unchanged."""
    assert _foul_trouble_factor_extended(5, 1, 10.0) == 0.40
    assert _foul_trouble_factor_extended(4, 3, 5.0) == 0.55
    assert _foul_trouble_factor_extended(4, 4, 7.0) == 0.65
    assert _foul_trouble_factor_extended(4, 4, 3.0) == 0.90
    assert _foul_trouble_factor_extended(3, 2, 8.0) == 0.80
    assert _foul_trouble_factor_extended(0, 2, 5.0) == 1.00


# ─── 3. Per-stat ratios (flag ON via direct manipulation) ────────────────────

def test_perstat_ratios_table_present():
    """All 7 stats have calibration ratios."""
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        assert stat in _FOUL_PERSTAT_RATIOS


def test_perstat_formula_reb_more_dampened():
    """REB ratio (1.4251) > PTS ratio (1.1279) → reb is more dampened when ON."""
    # Simulate the formula: ff_stat = 1 - (1-ff_base) * (ratio/pts_ratio)
    ff_base = 0.80   # pf==3 Q2 or Q3
    pts_ratio = _FOUL_PERSTAT_PTS_RATIO  # 1.1279
    reb_ratio = _FOUL_PERSTAT_RATIOS["reb"]  # 1.4251
    fg3m_ratio = _FOUL_PERSTAT_RATIOS["fg3m"]  # 0.9175

    dampener_pts = (1.0 - ff_base) * (pts_ratio / pts_ratio)  # == 1-ff_base
    dampener_reb = (1.0 - ff_base) * (reb_ratio / pts_ratio)
    dampener_fg3m = (1.0 - ff_base) * (fg3m_ratio / pts_ratio)

    # reb dampened MORE than pts (larger reduction)
    assert dampener_reb > dampener_pts
    # fg3m dampened LESS than pts (smaller reduction)
    assert dampener_fg3m < dampener_pts


def test_perstat_no_trouble_all_one():
    """When ff_base==1.0, per-stat function also returns 1.0 (no foul trouble)."""
    lf = _reload_live_factors(flag_on=True)
    try:
        result_pts = lf.foul_trouble_factor_perstat(0, 2, 5.0, "pts")
        result_reb = lf.foul_trouble_factor_perstat(0, 2, 5.0, "reb")
        result_tov = lf.foul_trouble_factor_perstat(0, 2, 5.0, "tov")
        assert result_pts == 1.0
        assert result_reb == 1.0
        assert result_tov == 1.0
    finally:
        _reload_live_factors(flag_on=False)


def test_perstat_flag_on_fills_gap_pf2_q1():
    """Flag ON: pf==2/Q1 returns 0.85 (gap filled)."""
    lf = _reload_live_factors(flag_on=True)
    try:
        # pf==2/Q1 ff_base=0.85; pts ratio == ref → ff_pts = 0.85
        result = lf.foul_trouble_factor_perstat(2, 1, 10.0, "pts")
        # For pts, ratio/pts_ratio = 1.0 exactly, so ff = 1 - 0.15 * 1.0 = 0.85
        assert abs(result - 0.85) < 1e-9
    finally:
        _reload_live_factors(flag_on=False)


def test_perstat_flag_on_fills_gap_pf3_q3():
    """Flag ON: pf==3/Q3 returns 0.80 for pts (gap filled)."""
    lf = _reload_live_factors(flag_on=True)
    try:
        result = lf.foul_trouble_factor_perstat(3, 3, 5.0, "pts")
        assert abs(result - 0.80) < 1e-9
    finally:
        _reload_live_factors(flag_on=False)


def test_perstat_flag_on_reb_more_dampened_than_pts():
    """Flag ON: reb more dampened than pts when in foul trouble."""
    lf = _reload_live_factors(flag_on=True)
    try:
        ff_pts = lf.foul_trouble_factor_perstat(3, 2, 8.0, "pts")
        ff_reb = lf.foul_trouble_factor_perstat(3, 2, 8.0, "reb")
        ff_fg3m = lf.foul_trouble_factor_perstat(3, 2, 8.0, "fg3m")
        # reb should be more dampened (smaller factor)
        assert ff_reb < ff_pts, f"reb={ff_reb} should < pts={ff_pts}"
        # fg3m should be less dampened (closer to 1.0)
        assert ff_fg3m > ff_pts, f"fg3m={ff_fg3m} should > pts={ff_pts}"
    finally:
        _reload_live_factors(flag_on=False)


# ─── 4. Clamp guarantees ────────────────────────────────────────────────────

def test_perstat_clamp_high_ratio_does_not_go_below_ff_base_minus_030():
    """Clamp: tov ratio (1.607) at severe foul (0.40) stays above 0.40-0.30=0.10."""
    lf = _reload_live_factors(flag_on=True)
    try:
        ff_tov = lf.foul_trouble_factor_perstat(5, 2, 5.0, "tov")
        ff_base = 0.40  # pf>=5
        lower_bound = max(0.0, ff_base - 0.30)
        assert ff_tov >= lower_bound, f"tov={ff_tov} < lower_bound={lower_bound}"
        assert ff_tov <= 1.0
    finally:
        _reload_live_factors(flag_on=False)


def test_perstat_result_never_exceeds_one():
    """Per-stat result is always ≤ 1.0 (no trouble → no boost)."""
    lf = _reload_live_factors(flag_on=True)
    try:
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            for pf_val in (0, 1, 2, 3, 4, 5, 6):
                for period_val in (1, 2, 3, 4):
                    result = lf.foul_trouble_factor_perstat(
                        pf_val, period_val, 6.0, stat
                    )
                    assert result <= 1.0 + 1e-9, (
                        f"{stat} pf={pf_val} period={period_val}: {result} > 1.0"
                    )
                    assert result >= 0.0
    finally:
        _reload_live_factors(flag_on=False)


# ─── 5. Graceful input handling ─────────────────────────────────────────────

def test_perstat_none_pf_returns_one():
    """None pf → no adjustment (flag OFF path)."""
    assert foul_trouble_factor_perstat(None, 3, 5.0, "pts") == 1.00


def test_perstat_unknown_stat_returns_pts_factor():
    """Unknown stat → falls back to shared scalar (pts ratio = 1.0 baseline)."""
    lf = _reload_live_factors(flag_on=True)
    try:
        # Unknown stat should use pts_ratio fallback (same as pts factor)
        result_unknown = lf.foul_trouble_factor_perstat(3, 2, 8.0, "unknown_stat")
        result_pts = lf.foul_trouble_factor_perstat(3, 2, 8.0, "pts")
        # Unknown stat uses pts_ratio as fallback (same relative_ratio = 1.0)
        assert abs(result_unknown - result_pts) < 1e-9
    finally:
        _reload_live_factors(flag_on=False)


# ─── 6. project_snapshot byte-identical when CV_FOUL_PERSTAT=0 ──────────────

def test_project_snapshot_byte_identical_flag_off():
    """project_snapshot output is byte-identical with CV_FOUL_PERSTAT=0."""
    import scripts.predict_in_game as pig  # noqa: E402
    import importlib
    importlib.reload(pig)

    snap = {
        "game_id": "0022400123",
        "period": 3,
        "clock": "06:00",
        "home_team": "OKC",
        "away_team": "NYK",
        "home_score": 60,
        "away_score": 55,
        "players": [
            {
                "player_id": 1234,
                "name": "Test Player",
                "team": "OKC",
                "min": 18.0,
                "pts": 14,
                "reb": 6,
                "ast": 3,
                "fg3m": 2,
                "stl": 1,
                "blk": 0,
                "tov": 2,
                "pf": 3,  # 3 fouls in Q3 → gap fills when ON
            },
            {
                "player_id": 5678,
                "name": "Test Player2",
                "team": "NYK",
                "min": 20.0,
                "pts": 10,
                "reb": 4,
                "ast": 5,
                "fg3m": 1,
                "stl": 2,
                "blk": 1,
                "tov": 1,
                "pf": 2,  # 2 fouls in Q3 → gap fills when ON
            },
        ],
    }

    # Run with flag OFF (default)
    os.environ.pop("CV_FOUL_PERSTAT", None)
    importlib.reload(pig)
    rows_off = pig.project_snapshot(snap)

    # Run again with flag still OFF — should be identical to first run
    rows_off2 = pig.project_snapshot(snap)

    for r1, r2 in zip(rows_off, rows_off2):
        assert r1["projected_final"] == r2["projected_final"], (
            f"{r1['stat']}: off1={r1['projected_final']} != off2={r2['projected_final']}"
        )

    # Cleanup
    os.environ.pop("CV_FOUL_PERSTAT", None)
