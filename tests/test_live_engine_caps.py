"""tests/test_live_engine_caps.py — Bug B regression tests.

Verifies that project_from_snapshot applies per-stat sane ceilings and
fg3m sqrt-damping, and that caps never push a projection below current.

These tests exercise the cap logic in isolation by monkeypatching
predict_in_game.project_snapshot to return controlled rows — no real
model artifacts or live API calls are needed.
"""
from __future__ import annotations

import sys
import os
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root and scripts/ on sys.path
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for d in (PROJECT_DIR, SCRIPTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)


def _make_stub_module(name: str) -> types.ModuleType:
    return types.ModuleType(name)


# ---------------------------------------------------------------------------
# Build a minimal predict_in_game stub so live_engine imports cleanly.
# Must be registered BEFORE live_engine is imported.
# ---------------------------------------------------------------------------
if "predict_in_game" not in sys.modules:
    pig_stub = types.ModuleType("predict_in_game")
    pig_stub.project_snapshot = lambda snap: []
    pig_stub.STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    pig_stub.parse_clock = lambda c: 0.0
    pig_stub.clock_played_share = lambda p, c: 0.5
    pig_stub.is_bench_in_current_period = lambda p, period, period_elapsed_min=0: False
    pig_stub.blowout_factor = lambda m, p, is_star=False: 1.0
    pig_stub.project_final = (
        lambda cur, period, clock, pace_factor=1, foul_factor=1,
               blow_factor=1, player_clock_played_min=None: cur
    )
    pig_stub.PERIOD_MIN = 12.0
    pig_stub.load_pregame_predictions = lambda d: {}
    sys.modules["predict_in_game"] = pig_stub

# ---------------------------------------------------------------------------
# Stub heavy optional sub-modules that live_engine imports lazily at call-time
# via try/except blocks.  We stub only the ones that would be reached through
# the live_engine import chain; we do NOT stub the real src.* package tree so
# the actual module path still resolves.
# ---------------------------------------------------------------------------
for _mod in ("lightgbm", "curl_cffi", "curl_cffi.requests"):
    if _mod not in sys.modules:
        sys.modules[_mod] = _make_stub_module(_mod)

# ---------------------------------------------------------------------------
# Import live_engine — this is the real module under test.
# ---------------------------------------------------------------------------
import importlib

# live_engine imports src.data.live at module-load time; that module must be
# importable.  If it isn't (e.g. missing parquet deps), stub just the three
# symbols live_engine uses.
try:
    from src.data import live as _live_data_mod   # noqa: F401 — ensure importable
except Exception:
    # Build a lightweight stand-in under the real package namespace.
    import src.data as _src_data_pkg
    _live_stub = types.ModuleType("src.data.live")
    _live_stub.list_today_snapshots = lambda d: []
    _live_stub.latest_snapshot_path = lambda d: None
    _live_stub.load_live_state = lambda p: {}
    sys.modules["src.data.live"] = _live_stub
    _src_data_pkg.live = _live_stub  # type: ignore[attr-defined]

live_engine = importlib.import_module("src.prediction.live_engine")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snap(period: int = 1, clock: str = "6:00") -> dict:
    """Minimal snapshot dict consumed by project_from_snapshot."""
    return {
        "period": period,
        "clock": clock,
        "home_team": "LAL",
        "away_team": "GSW",
        "home_score": 30,
        "away_score": 28,
        "players": [],
    }


def _make_row(stat: str, current: float, projected_final: float,
              player_id: int = 1) -> dict:
    return {
        "player_id": player_id,
        "name": "Test Player",
        "team": "LAL",
        "stat": stat,
        "current": current,
        "projected_final": projected_final,
        "snapshot_period": 1,
        "snapshot_clock": "6:00",
        "projection_source": "cycle_88_linear",
    }


def _run_caps(rows: List[Dict], snap: dict) -> List[Dict]:
    """Inject synthetic rows into project_from_snapshot by patching
    predict_in_game.project_snapshot and all post-processing overrides,
    then return the capped output rows.
    """
    with (
        patch.object(sys.modules["predict_in_game"], "project_snapshot",
                     return_value=[dict(r) for r in rows]),
        # Disable all the validated overlay / residual heads so only the cap
        # logic and floor-at-current are exercised.
        patch.object(live_engine, "_apply_unified_routed",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_period_heads",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_residual_heads_endq2",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_learned_q4_minutes",
                     side_effect=lambda s, r: (r, False)),
        patch.object(live_engine, "_apply_stratified_foul_residual",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_stratified_blowout_residual",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_heat_check_shrinkage",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_apply_residual_heads",
                     side_effect=lambda s, r: r),
        patch.object(live_engine, "_INCLUDE_QUANTILE_BANDS", False),
        patch.object(live_engine, "_USE_INPLAY_WINPROB", False),
    ):
        return live_engine.project_from_snapshot(snap)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStatCaps:
    """project_from_snapshot must clamp impossible projections to sane ceilings."""

    def test_pts_cap_applied(self):
        """Mid-Q1 10pts/6min extrapolating to pts=80 must be clamped to ≤70."""
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("pts", current=10.0, projected_final=80.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 70.0, f"pts cap not applied: projected_final={pf}"
        assert pf >= 10.0, f"pts went below current: projected_final={pf}"

    def test_fg3m_cap_applied(self):
        """Extrapolated fg3m=24 must be clamped to ≤14."""
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("fg3m", current=3.0, projected_final=24.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 14.0, f"fg3m cap not applied: projected_final={pf}"
        assert pf >= 3.0, f"fg3m went below current: projected_final={pf}"

    def test_reb_cap(self):
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("reb", current=5.0, projected_final=45.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 30.0
        assert pf >= 5.0

    def test_ast_cap(self):
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("ast", current=4.0, projected_final=50.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 25.0
        assert pf >= 4.0

    def test_stl_cap(self):
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("stl", current=1.0, projected_final=20.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 10.0
        assert pf >= 1.0

    def test_blk_cap(self):
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("blk", current=2.0, projected_final=30.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 12.0
        assert pf >= 2.0

    def test_tov_cap(self):
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("tov", current=1.0, projected_final=20.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 12.0
        assert pf >= 1.0


class TestCapNeverGoesBelowCurrent:
    """Caps must never lower a projection below the player's already-recorded stat."""

    def test_cap_floor_at_current_pts(self):
        """When projected_final is already reasonable, cap does not lower it."""
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("pts", current=20.0, projected_final=35.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf >= 20.0, f"projected_final {pf} went below current 20.0"
        assert pf <= 70.0

    def test_floor_at_current_when_projection_below_cap(self):
        """Projection well below cap stays unchanged."""
        snap = _make_snap(period=3, clock="6:00")  # mid-Q2
        rows_in = [_make_row("pts", current=18.0, projected_final=28.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf == pytest.approx(28.0, abs=0.5), (
            f"Reasonable projection was unexpectedly altered: {pf}"
        )


class TestFg3mSqrtDamping:
    """fg3m sqrt-damping must reduce impossible early projections."""

    def test_fg3m_damped_mid_q1(self):
        """Mid-Q1 (6 min elapsed): fg3m projection must be dampened AND ≤14."""
        snap = _make_snap(period=1, clock="6:00")   # 6 min into Q1 = 6 min elapsed
        rows_in = [_make_row("fg3m", current=3.0, projected_final=24.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        # After sqrt-damping, projection must be < raw linear and <= cap
        assert pf <= 14.0, f"fg3m cap not applied: {pf}"
        assert pf >= 3.0, f"fg3m went below current: {pf}"
        # The sqrt-damped value should also be strictly less than the linear projection
        assert pf < 24.0, f"sqrt-damping had no effect: still {pf}"

    def test_fg3m_not_damped_late_game(self):
        """Late in Q4 (period=4, clock≈0:30): no sqrt-damping, cap still applies."""
        snap = _make_snap(period=4, clock="0:30")   # ~47.5 min elapsed
        rows_in = [_make_row("fg3m", current=5.0, projected_final=16.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        # Cap applies but no sqrt-damping (minutes_elapsed >= 12)
        assert pf <= 14.0
        assert pf >= 5.0

    def test_fg3m_repro_case(self):
        """The exact repro: mid-Q1, 6min, 3fg3m → proj must be ≤14 and ≥ current."""
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("fg3m", current=3.0, projected_final=24.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 14.0
        assert pf >= 3.0   # floor-at-current invariant

    def test_pts_repro_case(self):
        """The exact repro: mid-Q1, 6min, 10pts → proj must be ≤70 and ≥ current."""
        snap = _make_snap(period=1, clock="6:00")
        rows_in = [_make_row("pts", current=10.0, projected_final=80.0)]
        out = _run_caps(rows_in, snap)
        pf = out[0]["projected_final"]
        assert pf <= 70.0
        assert pf >= 10.0
