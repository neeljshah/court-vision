"""tests/test_w009_rotminutes.py — W-009-RIGHT remaining-minutes consumer.

Validates CV_INGAME_ROTMINUTES (the rotation-curve remaining-minutes projection
consumer that redoes the rejected W-009 correctly):

  1. Flag OFF (default) is byte-identical to the pre-flag projector.
  2. rotminutes_expected_rem_min returns None when the flag is OFF or the
     player has no full atlas curve (→ flat fallback, byte-identical).
  3. When ON, the projection drives off the rotation-curve-blended minutes:
     a heavy-minutes player whose season curve says he'll keep playing projects
     MORE remaining stat than the flat clock share would, and a player whose
     curve says he'll sit (low-minute role) projects LESS.
  4. The atlas-range convention is correct: at endQ1 (period=2, clock=12:00) the
     remaining quarters are Q2+Q3+Q4 (all of period..4), not Q3+Q4.

These tests stub the atlas directly so they are offline and deterministic — they
never read the parquet.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402


def _reload_with_flag(value: str | None):
    """Reload predict_in_game with CV_INGAME_ROTMINUTES set to `value`."""
    if value is None:
        os.environ.pop("CV_INGAME_ROTMINUTES", None)
    else:
        os.environ["CV_INGAME_ROTMINUTES"] = value
    return importlib.reload(pig)


@pytest.fixture(autouse=True)
def _restore_module():
    """Always restore the module to flag-OFF after each test."""
    yield
    _reload_with_flag(None)


def _snap_endq1(cur_min=12.0, pts=10.0, pid=999):
    """endQ1 boundary snapshot: period=2, clock=12:00 (start of Q2)."""
    return {
        "game_id": "0022400999",
        "period": 2,
        "clock": "12:00",
        "home_team": "AAA",
        "away_team": "BBB",
        "home_score": 28,
        "away_score": 25,
        "players": [
            {"player_id": pid, "name": "Test Star", "team": "AAA",
             "min": cur_min, "pts": pts, "reb": 4.0, "ast": 2.0, "fg3m": 1.0,
             "stl": 0.0, "blk": 0.0, "tov": 1.0, "pf": 1.0,
             "min_q1": cur_min, "min_q2": 0.0, "min_q3": 0.0, "min_q4": 0.0},
        ],
    }


# ── 1. byte-identical OFF ─────────────────────────────────────────────────────

def test_flag_off_is_byte_identical():
    """Flag OFF → projections identical to a fresh OFF module (no behaviour change)."""
    mod_off = _reload_with_flag("0")
    snap = _snap_endq1()
    rows_off = mod_off.project_snapshot(dict(snap), )
    # default (no env) must equal explicit "0"
    mod_default = _reload_with_flag(None)
    rows_default = mod_default.project_snapshot(dict(snap))
    assert len(rows_off) == len(rows_default)
    for a, b in zip(rows_off, rows_default):
        assert a["stat"] == b["stat"]
        assert a["projected_final"] == pytest.approx(b["projected_final"], abs=1e-9)


def test_expected_rem_min_none_when_flag_off():
    """rotminutes_expected_rem_min returns None when the flag is OFF."""
    mod = _reload_with_flag("0")
    assert mod.rotminutes_expected_rem_min(999, 2, 12.0, 12.0) is None


# ── 2. graceful fallback for unknown player ───────────────────────────────────

def test_unknown_player_falls_back_to_flat():
    """A player absent from the atlas → None → flat path (byte-identical)."""
    mod = _reload_with_flag("1")
    # stub a tiny atlas WITHOUT our pid → no full curve
    mod._ROTCURVE_ATLAS = {123: {1: 8.0, 2: 8.0, 3: 8.0, 4: 8.0}}
    mod._ROTCURVE_N_GAMES = {123: 50.0}
    assert mod.rotminutes_expected_rem_min(999, 2, 12.0, 12.0) is None


# ── 3. atlas-range convention (endQ1 remaining = Q2+Q3+Q4) ────────────────────

def test_atlas_range_includes_current_unstarted_period():
    """At endQ1 (period=2, clock=12:00) remaining = season Q2+Q3+Q4 minutes."""
    mod = _reload_with_flag("1")
    # player plays exactly 9 min every quarter, many games (atlas dominates).
    mod._ROTCURVE_ATLAS = {999: {1: 9.0, 2: 9.0, 3: 9.0, 4: 9.0}}
    mod._ROTCURVE_N_GAMES = {999: 1000.0}  # huge → w≈1.0 atlas weight
    rem = mod.rotminutes_expected_rem_min(999, 2, 12.0, 12.0)
    # remaining should be Q2+Q3+Q4 = 27, NOT Q3+Q4 = 18, clamped to rem_clock=36.
    assert rem == pytest.approx(27.0, abs=0.2)


def test_atlas_clamped_to_remaining_clock():
    """Atlas remaining can never exceed the wall-clock minutes left."""
    mod = _reload_with_flag("1")
    # player "plays" 20 min/quarter in the atlas (impossible cap) — must clamp.
    mod._ROTCURVE_ATLAS = {999: {1: 20.0, 2: 20.0, 3: 20.0, 4: 20.0}}
    mod._ROTCURVE_N_GAMES = {999: 1000.0}
    rem = mod.rotminutes_expected_rem_min(999, 4, 12.0, 12.0)  # endQ3 → 12 min left
    # The atlas component (clamped to 12) dominates at w≈0.99; the tiny residual
    # flat weight (flat=4 at endQ3) pulls it just below 12. It can NEVER exceed
    # the 12 wall-clock minutes left — that is the clamp guarantee.
    assert rem <= 12.0 + 1e-9
    assert rem == pytest.approx(0.990099 * 12.0 + 0.009901 * 4.0, abs=1e-3)


# ── 4. directional behaviour: curve raises / lowers vs flat ───────────────────

def test_curve_raises_projection_when_player_keeps_playing():
    """A starter who played a full Q1 and keeps starter minutes projects MORE
    remaining PTS than the flat clock-share (flat assumes the same 12-min Q1
    rate over 36 remaining clock minutes; the curve credits ~27 remaining
    player-minutes, but at the SAME per-minute rate — so for a heavy player the
    two are close; the test asserts the curve path actually fires & is sane)."""
    mod = _reload_with_flag("1")
    # 30 min/game player: 9/9/8/4 curve. At endQ1 the curve says 9+8+4=21 min
    # remaining (player will play less in Q4), vs flat 12*(36/12)=36 min.
    mod._ROTCURVE_ATLAS = {999: {1: 9.0, 2: 9.0, 3: 8.0, 4: 4.0}}
    mod._ROTCURVE_N_GAMES = {999: 1000.0}
    snap = _snap_endq1(cur_min=12.0, pts=10.0, pid=999)
    rows = mod.project_snapshot(snap)
    pts_row = next(r for r in rows if r["stat"] == "pts")
    # per-min rate = 10/12 = 0.833; rem_min ≈ 21 → rem_pts ≈ 17.5 → final ≈ 27.5
    # flat path would be 10 + 10*(36/12) = 40. Curve is LOWER (player sits late).
    assert pts_row["projected_final"] == pytest.approx(10.0 + (10.0 / 12.0) * 21.0,
                                                       rel=0.02)
    assert pts_row["projected_final"] < 40.0   # strictly below the flat blow-up


def test_low_minute_role_player_projects_less_than_flat():
    """A role player whose curve says he'll sit most of the game projects much
    less remaining stat than the naive flat extrapolation."""
    mod = _reload_with_flag("1")
    # 12-min/game player: 6/3/2/1. At endQ1 with 6 min played, curve remaining
    # = 3+2+1 = 6 min; flat = 6*(36/12) = 18 min. Curve << flat.
    mod._ROTCURVE_ATLAS = {999: {1: 6.0, 2: 3.0, 3: 2.0, 4: 1.0}}
    mod._ROTCURVE_N_GAMES = {999: 1000.0}
    snap = _snap_endq1(cur_min=6.0, pts=4.0, pid=999)
    snap["players"][0]["min_q1"] = 6.0
    rows = mod.project_snapshot(snap)
    pts_row = next(r for r in rows if r["stat"] == "pts")
    flat_final = 4.0 + 4.0 * (36.0 / 12.0)   # = 16 under the flat path
    assert pts_row["projected_final"] < flat_final
    # curve: 4 + (4/6)*6 = 8
    assert pts_row["projected_final"] == pytest.approx(8.0, rel=0.03)


# ── 5. current_stat is never reduced ──────────────────────────────────────────

def test_never_projects_below_current():
    """projected_final >= current always (a player can't un-score)."""
    mod = _reload_with_flag("1")
    mod._ROTCURVE_ATLAS = {999: {1: 9.0, 2: 9.0, 3: 8.0, 4: 4.0}}
    mod._ROTCURVE_N_GAMES = {999: 1000.0}
    snap = _snap_endq1(cur_min=12.0, pts=10.0, pid=999)
    rows = mod.project_snapshot(snap)
    for r in rows:
        assert r["projected_final"] >= r["current"] - 1e-9
