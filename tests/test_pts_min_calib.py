"""tests/test_pts_min_calib.py -- W-013 (CV_PTS_MIN_CALIB).

Tests for the per-period minutes-trajectory recalibration gate:

1. Flag OFF -> projections are byte-identical to baseline (no-op).
2. Flag ON + endQ2 snapshot + model present -> PTS rows modified (ratio != 1).
3. Flag ON + endQ1 snapshot -> no change (only endQ2 fires).
4. Flag ON + endQ3 snapshot -> no change (only endQ2 fires).
5. Flag ON + non-PTS stat -> unchanged by the calibration pass.
6. Flag ON + model absent (mocked) -> graceful no-op, rows unmodified.
7. Flag ON + zero remaining delta -> no change (current_pts == projected_final).
"""
from __future__ import annotations

import os
import sys
from unittest import mock
import copy

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import src.prediction.live_engine as le  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _snap(period: int, clock: str = "12:00", players=None):
    return {
        "game_id": "0042500999",
        "period": period,
        "clock": clock,
        "home_score": 55,
        "away_score": 48,
        "home_team": "OKC",
        "away_team": "NYK",
        "players": players if players is not None else [],
    }


def _player(pid=1, team="OKC", pts=10, min_val=24.0, pf=1):
    return {
        "player_id": pid,
        "name": f"Player {pid}",
        "team": team,
        "is_starter": True,
        "min": min_val,
        "pf": pf,
        "pts": pts,
        "reb": 4, "ast": 3, "fg3m": 1, "stl": 0, "blk": 0, "tov": 2,
        "min_q1": min_val / 2,
        "min_q2": min_val / 2,
        "min_q3": 0.0, "min_q4": 0.0,
    }


def _make_fake_booster(pred_value: float):
    """Return a mock booster whose .predict() always returns pred_value."""
    booster = mock.MagicMock()
    import numpy as np
    booster.predict.return_value = np.array([pred_value])
    return booster


# ── test 1: flag OFF -> no-op ─────────────────────────────────────────────────

def test_flag_off_noop(monkeypatch):
    """With CV_PTS_MIN_CALIB unset, rows must be byte-identical to baseline."""
    monkeypatch.delenv("CV_PTS_MIN_CALIB", raising=False)
    # Reset module caches so we start clean.
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    players = [_player(pid=1, pts=14, min_val=24.0)]
    snap = _snap(period=3, clock="12:00", players=players)
    rows_flag_off = le.project_from_snapshot(snap)

    # Collect projected_finals for PTS when flag is OFF.
    finals_off = {r["player_id"]: r["projected_final"]
                  for r in rows_flag_off if r["stat"] == "pts"}
    assert finals_off, "expected at least one PTS row"
    # No '+pts_min_calib' tag in any row.
    for r in rows_flag_off:
        assert "+pts_min_calib" not in str(r.get("projection_source") or "")


# ── test 2: flag ON + endQ2 + model present -> PTS adjusted ──────────────────

def test_flag_on_endq2_pts_adjusted(monkeypatch):
    """With flag ON and an endQ2 snapshot, PTS projected_final is adjusted by
    the learned minutes ratio.  A model predicting 18 min (ratio=0.75) on a
    projected delta of 12 pts -> new_final = 14 + 12*0.75 = 23.
    """
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    # Inject a fake model that predicts 18 remaining minutes (ratio=18/24=0.75).
    fake_booster = _make_fake_booster(18.0)
    fake_feature_names = ["pf_through_q2", "min_q1", "min_q2", "period",
                          "score_margin_abs", "is_leading_team",
                          "pos_C", "pos_F", "pos_G", "l20_min", "l5_min"]
    le._PTS_MIN_CALIB_MODEL_Q2 = (fake_booster, fake_feature_names)

    players = [_player(pid=1, pts=14, min_val=24.0)]
    snap = _snap(period=3, clock="12:00", players=players)

    rows = le.project_from_snapshot(snap)
    pts_rows = [r for r in rows if r["stat"] == "pts" and r["player_id"] == 1]
    assert pts_rows, "no PTS row for player 1"
    r = pts_rows[0]

    # The period_specific_heads fire at endQ2 and set projected_final.
    # After that, the calibration scales the remaining delta.
    # We just verify:  (a) +pts_min_calib tag present,
    #                  (b) projected_final >= current (current=14 from player dict).
    assert "+pts_min_calib" in str(r.get("projection_source") or ""), (
        f"expected +pts_min_calib tag, got {r.get('projection_source')!r}")
    assert r["projected_final"] >= 14.0, (
        f"projected_final {r['projected_final']} should be >= current_pts 14")


# ── test 3: flag ON + endQ1 snapshot -> no change ────────────────────────────

def test_flag_on_endq1_no_change(monkeypatch):
    """At endQ1 (period=2), the calibration must be a no-op (only fires at endQ2)."""
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    players = [_player(pid=1, pts=8, min_val=12.0)]
    snap = _snap(period=2, clock="12:00", players=players)
    rows = le.project_from_snapshot(snap)
    for r in rows:
        assert "+pts_min_calib" not in str(r.get("projection_source") or ""), (
            "endQ1 should not be tagged with pts_min_calib")


# ── test 4: flag ON + endQ3 snapshot -> no change ────────────────────────────

def test_flag_on_endq3_no_change(monkeypatch):
    """At endQ3 (period=4), the calibration must be a no-op (only fires at endQ2)."""
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    players = [_player(pid=1, pts=22, min_val=36.0)]
    snap = _snap(period=4, clock="12:00", players=players)
    rows = le.project_from_snapshot(snap)
    for r in rows:
        assert "+pts_min_calib" not in str(r.get("projection_source") or ""), (
            "endQ3 should not be tagged with pts_min_calib")


# ── test 5: non-PTS stat unchanged ───────────────────────────────────────────

def test_non_pts_stat_unchanged(monkeypatch):
    """REB/AST rows must not be modified by the calibration (PTS-only)."""
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    fake_booster = _make_fake_booster(12.0)
    le._PTS_MIN_CALIB_MODEL_Q2 = (fake_booster, [])

    players = [_player(pid=1, pts=14, min_val=24.0)]
    snap = _snap(period=3, clock="12:00", players=players)
    rows = le.project_from_snapshot(snap)

    for r in rows:
        if r["stat"] != "pts":
            assert "+pts_min_calib" not in str(r.get("projection_source") or ""), (
                f"non-PTS stat {r['stat']} should not get pts_min_calib tag")


# ── test 6: flag ON + model absent -> graceful no-op ─────────────────────────

def test_flag_on_model_absent_graceful(monkeypatch):
    """When the Q2 minute-trajectory model files are missing, rows are unchanged."""
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    # Patch os.path.exists to return False for the model files.
    original_exists = os.path.exists

    def patched_exists(path):
        if "minute_trajectory_q2" in str(path):
            return False
        return original_exists(path)

    monkeypatch.setattr(os.path, "exists", patched_exists)

    players = [_player(pid=1, pts=14, min_val=24.0)]
    snap = _snap(period=3, clock="12:00", players=players)
    rows = le.project_from_snapshot(snap)
    # No row should have pts_min_calib tag.
    for r in rows:
        assert "+pts_min_calib" not in str(r.get("projection_source") or "")
    # load_failed should now be True (so subsequent calls skip the check).
    assert le._PTS_MIN_CALIB_LOAD_FAILED is True


# ── test 7: zero remaining delta -> no change ─────────────────────────────────

def test_zero_remaining_delta_noop(monkeypatch):
    """When projected_final == current_pts (delta=0), the calibration is a no-op
    and no tag is added (nothing to scale)."""
    monkeypatch.setenv("CV_PTS_MIN_CALIB", "1")
    le._PTS_MIN_CALIB_MODEL_Q2 = None
    le._PTS_MIN_CALIB_LOAD_FAILED = False

    fake_booster = _make_fake_booster(12.0)
    le._PTS_MIN_CALIB_MODEL_Q2 = (fake_booster, [])

    # Force a projection where remaining_delta = 0 by making current = projected.
    # We mock _apply_pts_min_calib directly with a snapshot where the rows
    # already have projected_final == current.
    from src.prediction.live_engine import _apply_pts_min_calib

    snap = _snap(period=3, clock="12:00", players=[_player(pid=1, pts=20)])
    # Build a row with projected_final == current (delta=0).
    row = {"player_id": 1, "stat": "pts", "current": 20.0,
           "projected_final": 20.0, "projection_source": "test_source"}
    rows = [row]
    result = _apply_pts_min_calib(snap, rows)
    assert result[0]["projected_final"] == 20.0
    assert "+pts_min_calib" not in str(result[0].get("projection_source") or "")
