"""tests/test_live_engine_period_heads.py -- cycle 106a (loop 5).

Tests that src.prediction.live_engine.project_from_snapshot dispatches to
the cycle-105b period_specific_heads at endQ1 and endQ2 boundaries, and
falls back to the cycle-88 linear extrapolator everywhere else (mid-quarter,
endQ3, missing artifact, flag off).
"""
from __future__ import annotations

import os
import sys
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction import live_engine                      # noqa: E402
from src.prediction import period_specific_heads as psh     # noqa: E402


def _snapshot(period, clock, players=None):
    return {
        "game_id": "0022400999",
        "captured_at": "2026-05-24T20:00:00",
        "game_status": "LIVE",
        "period": period, "clock": clock,
        "home_score": 30, "away_score": 25,
        "home_team": "OKC", "away_team": "SAS",
        "players": players if players is not None else [],
    }


def _player(pid=1, team="OKC", **overrides):
    base = {
        "name": f"Player {pid}", "player_id": pid, "team": team,
        "is_starter": True, "min": 9.0, "pf": 1,
        "pts": 8, "reb": 3, "ast": 2, "fg3m": 1, "stl": 0, "blk": 0, "tov": 1,
        "min_q1": 9.0, "min_q2": 0.0, "min_q3": 0.0, "min_q4": 0.0,
    }
    base.update(overrides)
    return base


def _stub_predict_remaining(monkeypatch):
    """Force period_specific_heads.predict_remaining to deterministic stub.

    Returns 5.5 (any non-None float) so projections are reproducibly
    overridden whenever the heads dispatch fires.
    """
    psh.reset_cache()
    monkeypatch.setattr(psh, "predict_remaining",
                        lambda *a, **kw: 5.5)


def _stub_predict_remaining_none(monkeypatch):
    """Simulate missing artifact -> predict_remaining returns None."""
    psh.reset_cache()
    monkeypatch.setattr(psh, "predict_remaining",
                        lambda *a, **kw: None)


# ── 1. endQ1 snapshot -> projection_source == endQ1_head ─────────────────────

def test_endQ1_snapshot_uses_endQ1_head(monkeypatch):
    _stub_predict_remaining(monkeypatch)
    snap = _snapshot(period=2, clock="12:00",
                     players=[_player(pid=1, pts=10, min_q1=10.0, min=10.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    assert sources == {"endQ1_head"}
    # current_stat (10) + remaining stub (5.5) = 15.5 for pts
    pts_row = next(r for r in rows if r["stat"] == "pts")
    assert pts_row["projected_final"] == 15.5


# ── 2. endQ2 snapshot -> projection_source == endQ2_head ─────────────────────

def test_endQ2_snapshot_uses_endQ2_head(monkeypatch):
    _stub_predict_remaining(monkeypatch)
    snap = _snapshot(period=3, clock="12:00",
                     players=[_player(pid=1, pts=18, min_q1=10.0,
                                      min_q2=10.0, min=20.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    assert sources == {"endQ2_head"}


# ── 3. endQ3 snapshot -> projection_source stays cycle_88_linear ─────────────

def test_endQ3_snapshot_keeps_cycle_88_linear(monkeypatch):
    """cycle 105b explicitly REJECTED the endQ3 period head; back-compat preserved.

    cycle R2_F update: projection_source may now carry a "+residual_head" suffix
    at endQ3 (period=4) -- the key constraint is that NO source starts with
    "endQ3_head" (the rejected period head) and that every source is either a
    plain variant or one of the valid endQ3 sources (learned_q4_minutes_v1,
    cycle_88_linear) optionally suffixed with "+residual_head".
    """
    _stub_predict_remaining(monkeypatch)
    snap = _snapshot(period=4, clock="12:00",
                     players=[_player(pid=1, pts=26, min_q1=10.0,
                                      min_q2=10.0, min_q3=10.0, min=30.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    # The endQ3 period-specific head was rejected (cycle 105b); no source should
    # start with "endQ3_head".
    for src in sources:
        assert not src.startswith("endQ3_head"), (
            f"endQ3 period head should not fire, got: {src}"
        )
    # Every source must be one of the valid endQ3 variants (with optional
    # +residual_head suffix from cycle R2_F).
    valid_bases = {"cycle_88_linear", "learned_q4_minutes_v1"}
    for src in sources:
        base = src.replace("+residual_head", "")
        assert base in valid_bases, f"Unexpected projection_source at endQ3: {src}"


# ── 4. Mid-quarter snapshot -> projection_source == cycle_88_linear ──────────

def test_mid_quarter_snapshot_keeps_cycle_88_linear(monkeypatch):
    _stub_predict_remaining(monkeypatch)
    snap = _snapshot(period=2, clock="5:00",
                     players=[_player(pid=1, pts=14, min_q1=10.0,
                                      min_q2=7.0, min=17.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    assert sources == {"cycle_88_linear"}


# ── 5. Missing artifact -> graceful fall through to cycle_88_linear ──────────

def test_missing_artifact_falls_through(monkeypatch):
    _stub_predict_remaining_none(monkeypatch)
    snap = _snapshot(period=2, clock="12:00",
                     players=[_player(pid=1, pts=10, min_q1=10.0, min=10.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    assert sources == {"cycle_88_linear"}


# ── 6. _USE_PERIOD_HEADS = False -> all rows are cycle_88_linear ─────────────

def test_flag_off_disables_period_heads(monkeypatch):
    _stub_predict_remaining(monkeypatch)
    monkeypatch.setattr(live_engine, "_USE_PERIOD_HEADS", False)
    snap = _snapshot(period=2, clock="12:00",
                     players=[_player(pid=1, pts=10, min_q1=10.0, min=10.0)])
    rows = live_engine.project_from_snapshot(snap)
    sources = {r["projection_source"] for r in rows
               if r["stat"] in psh.STATS}
    assert sources == {"cycle_88_linear"}
