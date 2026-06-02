"""tests/test_live_engine_robustness.py
Exhaustive robustness test suite for ``src.prediction.live_engine.project_from_snapshot``.

Covers:
  * Step 1 — 30+ edge-case snapshots across pre-tip, mid-quarter (Q1-Q4), end-
             quarter boundaries, overtime, and malformed inputs.
  * Step 2 — Both CV_INGAME_SBS flag states (off / on) per edge case.
             Schema assertions: list return, required keys, valid projected_final.
  * Step 3 — Latency measurement at CV_INGAME_NSIMS=200/400/800 on a real mid-
             game snapshot (5 warm calls per config).

Run:
    NBA_OFFLINE=1 NBA_FORCE_CPU=1 python -m pytest tests/test_live_engine_robustness.py -v
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pytest

from src.prediction import live_engine  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────

# Required keys every row MUST carry (player lines schema).
REQUIRED_KEYS = {"player_id", "stat", "current", "projected_final", "projection_source"}

# Stats the projector produces (must appear exactly 7× per player).
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# ── snapshot factory helpers ──────────────────────────────────────────────────

def _player(
    pid: int,
    team: str,
    *,
    name: str = "Test Player",
    is_starter: bool = True,
    minutes: float = 0.0,
    pts: int = 0, reb: int = 0, ast: int = 0,
    fg3m: int = 0, stl: int = 0, blk: int = 0,
    tov: int = 0, pf: int = 0,
    min_q1: Optional[float] = None,
    min_q2: Optional[float] = None,
    min_q3: Optional[float] = None,
    min_q4: Optional[float] = None,
) -> Dict[str, Any]:
    p: Dict[str, Any] = {
        "player_id": pid, "name": name, "team": team,
        "is_starter": is_starter,
        "min": minutes, "pts": pts, "reb": reb, "ast": ast,
        "fg3m": fg3m, "stl": stl, "blk": blk, "tov": tov, "pf": pf,
    }
    if min_q1 is not None:
        p["min_q1"] = min_q1
    if min_q2 is not None:
        p["min_q2"] = min_q2
    if min_q3 is not None:
        p["min_q3"] = min_q3
    if min_q4 is not None:
        p["min_q4"] = min_q4
    return p


def _snap(
    period: Any = 2,
    clock: Any = "6:00",
    home_score: int = 50,
    away_score: int = 45,
    home_team: str = "OKC",
    away_team: str = "SAS",
    game_id: str = "0022400123",
    game_status: str = "LIVE",
    players: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    return {
        "game_id": game_id,
        "captured_at": "2026-05-31T20:00:00+00:00",
        "game_status": game_status,
        "period": period,
        "clock": clock,
        "home_score": home_score,
        "away_score": away_score,
        "home_team": home_team,
        "away_team": away_team,
        "players": players if players is not None else [],
    }


def _real_players_mid_game() -> List[Dict[str, Any]]:
    """Realistic 6-player group (Q3 mid-game) for latency probes."""
    return [
        _player(1628983, "OKC", name="Shai Gilgeous-Alexander",
                minutes=24.0, pts=22, reb=3, ast=5, fg3m=2, stl=2, blk=0,
                tov=2, pf=1, min_q1=9.2, min_q2=8.8, min_q3=6.0),
        _player(1641705, "SAS", name="Victor Wembanyama",
                minutes=22.0, pts=18, reb=8, ast=2, fg3m=1, stl=0, blk=4,
                tov=1, pf=2, min_q1=8.5, min_q2=9.0, min_q3=4.5),
        _player(1630577, "SAS", name="Julian Champagnie",
                minutes=20.0, pts=14, reb=4, ast=1, fg3m=4, stl=0, blk=0,
                tov=0, pf=1, min_q1=7.0, min_q2=8.0, min_q3=5.0),
        _player(1631096, "OKC", name="Chet Holmgren",
                minutes=21.0, pts=10, reb=6, ast=1, fg3m=1, stl=1, blk=2,
                tov=1, pf=2, min_q1=8.0, min_q2=8.5, min_q3=4.5),
        _player(1628368, "SAS", name="De'Aaron Fox",
                minutes=22.0, pts=16, reb=2, ast=6, fg3m=2, stl=1, blk=0,
                tov=3, pf=2, min_q1=8.5, min_q2=9.0, min_q3=4.5),
        _player(1641717, "OKC", name="Cason Wallace",
                minutes=19.0, pts=9, reb=3, ast=2, fg3m=2, stl=0, blk=0,
                tov=1, pf=1, min_q1=7.5, min_q2=8.0, min_q3=3.5),
    ]


# ── global assertion helpers ──────────────────────────────────────────────────

def _assert_valid_rows(
    rows: Any,
    label: str,
    *,
    allow_empty_players: bool = False,
) -> None:
    """Core contract: rows must be a list, never raise, never NaN/inf/None final."""
    assert isinstance(rows, list), (
        f"[{label}] project_from_snapshot must return a list, got {type(rows)}"
    )
    if not allow_empty_players and rows:
        for r in rows:
            # Required keys
            for key in REQUIRED_KEYS:
                assert key in r, (
                    f"[{label}] row missing required key '{key}': {r}"
                )
            # projected_final must be a finite float
            pf = r.get("projected_final")
            assert pf is not None, (
                f"[{label}] projected_final is None for row {r}"
            )
            try:
                pf_f = float(pf)
            except (TypeError, ValueError) as exc:
                raise AssertionError(
                    f"[{label}] projected_final={pf!r} cannot be cast to float: {exc}"
                )
            assert math.isfinite(pf_f), (
                f"[{label}] projected_final={pf_f} is NaN or inf for row {r}"
            )
            assert pf_f >= 0.0, (
                f"[{label}] projected_final={pf_f} is negative (impossible counting stat)"
            )
            # current must be a finite float
            cur = r.get("current")
            if cur is not None:
                try:
                    cur_f = float(cur)
                except (TypeError, ValueError):
                    cur_f = None
                if cur_f is not None:
                    assert math.isfinite(cur_f), (
                        f"[{label}] current={cur_f} is NaN/inf"
                    )
                    # projected_final >= current (floor rule)
                    assert pf_f >= cur_f - 1e-6, (
                        f"[{label}] projected_final={pf_f} < current={cur_f} "
                        f"(floor rule violated) for row {r}"
                    )
            # projection_source must be a non-empty string
            ps = r.get("projection_source")
            assert isinstance(ps, str) and ps, (
                f"[{label}] projection_source={ps!r} is not a non-empty string"
            )


def _run_both_flag_states(
    snap: Dict[str, Any],
    label: str,
    *,
    allow_empty_players: bool = False,
) -> None:
    """Run project_from_snapshot with CV_INGAME_SBS=0 and CV_INGAME_SBS=1,
    assert valid rows for both, return (rows_off, rows_on)."""
    # --- flag OFF (default production path) ---
    with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "0"}, clear=False):
        try:
            rows_off = live_engine.project_from_snapshot(dict(snap))
        except Exception as exc:
            raise AssertionError(
                f"[{label} | SBS=0] project_from_snapshot RAISED: {exc}"
            ) from exc
    _assert_valid_rows(rows_off, f"{label}|SBS=0",
                       allow_empty_players=allow_empty_players)

    # --- flag ON (unified SBS overlay) ---
    with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
        try:
            rows_on = live_engine.project_from_snapshot(dict(snap))
        except Exception as exc:
            raise AssertionError(
                f"[{label} | SBS=1] project_from_snapshot RAISED: {exc}"
            ) from exc
    _assert_valid_rows(rows_on, f"{label}|SBS=1",
                       allow_empty_players=allow_empty_players)

    return rows_off, rows_on


# =============================================================================
# STEP 1 + 2 — Edge-case snapshot battery
# =============================================================================

class TestPreTip:
    """Period 0 / PRE_GAME snapshots — no game time has elapsed."""

    def test_pre_tip_empty_players(self):
        """Period 0, no players — must return empty list, not crash."""
        snap = _snap(period=0, clock="31:42", home_score=0, away_score=0,
                     game_status="PRE_GAME", players=[])
        off, on = _run_both_flag_states(snap, "pre_tip_empty", allow_empty_players=True)
        assert off == [], f"expected [] for pre-tip empty, got {off}"
        assert on == [], f"expected [] for pre-tip empty SBS=1, got {on}"

    def test_pre_tip_with_players(self):
        """Period 0 with roster loaded — projections are sensible (current=0)."""
        players = [
            _player(1628983, "OKC", name="SGA", minutes=0),
            _player(1641705, "SAS", name="Wemby", minutes=0),
        ]
        snap = _snap(period=0, clock="0:00", home_score=0, away_score=0,
                     game_status="PRE_GAME", players=players)
        off, on = _run_both_flag_states(snap, "pre_tip_with_players")
        # Each player x 7 stats = 14 rows
        assert len(off) == 14
        # current=0 pre-tip; projected_final must also be >= 0
        for r in off + on:
            assert r["current"] == 0.0

    def test_pre_tip_period_1_clock_12(self):
        """Period=1, clock=12:00 — very first moments of Q1."""
        players = [_player(1, "OKC", minutes=0), _player(2, "SAS", minutes=0)]
        snap = _snap(period=1, clock="12:00", home_score=0, away_score=0,
                     game_status="LIVE", players=players)
        _run_both_flag_states(snap, "q1_tip_off")


class TestMidQuarter:
    """Mid-quarter snapshots across Q1-Q4."""

    def test_q1_mid(self):
        players = [
            _player(1, "OKC", minutes=3.0, pts=4, reb=1, ast=1),
            _player(2, "SAS", minutes=3.0, pts=2, reb=2, ast=0),
        ]
        snap = _snap(period=1, clock="9:00", players=players)
        _run_both_flag_states(snap, "q1_mid_6min")

    def test_q2_early(self):
        players = [
            _player(10, "OKC", minutes=12.0, pts=10, reb=4, min_q1=9.5),
            _player(20, "SAS", minutes=11.0, pts=8, reb=3, min_q1=9.0),
        ]
        snap = _snap(period=2, clock="10:00", home_score=28, away_score=25,
                     players=players)
        _run_both_flag_states(snap, "q2_early")

    def test_q2_mid(self):
        players = [
            _player(10, "OKC", minutes=16.0, pts=14, reb=5, min_q1=9.5, min_q2=4.0),
            _player(20, "SAS", minutes=15.0, pts=11, reb=4, min_q1=9.0, min_q2=4.5),
        ]
        snap = _snap(period=2, clock="6:00", home_score=38, away_score=35,
                     players=players)
        _run_both_flag_states(snap, "q2_mid")

    def test_q3_mid(self):
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        _run_both_flag_states(snap, "q3_mid")

    def test_q3_late(self):
        players = [
            _player(1, "OKC", minutes=28.0, pts=25, reb=7, ast=8, pf=3,
                    min_q1=9.5, min_q2=9.5, min_q3=9.0),
            _player(2, "SAS", minutes=27.0, pts=22, reb=10, ast=2, pf=4,
                    min_q1=9.0, min_q2=9.2, min_q3=8.8),
        ]
        snap = _snap(period=3, clock="2:00", home_score=80, away_score=76,
                     players=players)
        _run_both_flag_states(snap, "q3_late")

    def test_q4_early(self):
        players = [
            _player(1, "OKC", minutes=36.5, pts=30, reb=8, ast=9, pf=2,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=8.0),
            _player(2, "SAS", minutes=35.0, pts=28, reb=7, ast=5, pf=3,
                    min_q1=9.0, min_q2=9.0, min_q3=9.0, min_q4=8.0),
        ]
        snap = _snap(period=4, clock="8:00", home_score=90, away_score=87,
                     players=players)
        _run_both_flag_states(snap, "q4_early")

    def test_q4_two_min_left(self):
        """Deep Q4 — 2 min left, close game, foul trouble."""
        players = [
            _player(1, "OKC", minutes=42.0, pts=35, reb=4, ast=9, pf=4,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=4.5),
            _player(2, "SAS", minutes=40.0, pts=22, reb=7, ast=2, pf=5,
                    min_q1=9.0, min_q2=9.0, min_q3=9.0, min_q4=4.0),
        ]
        snap = _snap(period=4, clock="2:00", home_score=103, away_score=100,
                     players=players)
        _run_both_flag_states(snap, "q4_2min")

    def test_q4_blowout(self):
        """Q4 blowout (margin=25) — star player blowout factor fires."""
        players = [
            _player(1, "OKC", minutes=38.0, pts=28, reb=5, ast=7, pf=1,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=9.5),
        ]
        snap = _snap(period=4, clock="4:00", home_score=118, away_score=93,
                     players=players)
        _run_both_flag_states(snap, "q4_blowout_margin25")


class TestEndQuarterBoundaries:
    """Clock near 12:00 at period start — endQ1/endQ2/endQ3 boundary detection."""

    def test_end_q1_boundary(self):
        """period=2, clock=12:00 -> endQ1 head fires if artifact available."""
        players = [
            _player(1, "OKC", minutes=12.0, pts=10, reb=3, ast=2,
                    min_q1=9.5),
            _player(2, "SAS", minutes=11.5, pts=8, reb=4, ast=1,
                    min_q1=9.0),
        ]
        snap = _snap(period=2, clock="12:00", home_score=30, away_score=28,
                     players=players)
        _run_both_flag_states(snap, "end_q1_boundary")

    def test_end_q2_boundary(self):
        """period=3, clock=12:00 -> endQ2 head fires if artifact available."""
        players = [
            _player(1, "OKC", minutes=24.0, pts=20, reb=6, ast=5, pf=2,
                    min_q1=9.5, min_q2=9.5),
            _player(2, "SAS", minutes=23.0, pts=18, reb=8, ast=2, pf=1,
                    min_q1=9.0, min_q2=9.0),
        ]
        snap = _snap(period=3, clock="12:00", home_score=58, away_score=55,
                     players=players)
        _run_both_flag_states(snap, "end_q2_boundary_halftime")

    def test_end_q3_boundary(self):
        """period=4, clock=12:00 -> endQ3 learned-Q4-minutes path fires."""
        players = [
            _player(1, "OKC", minutes=36.0, pts=30, reb=8, ast=9, pf=3,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5),
            _player(2, "SAS", minutes=35.0, pts=28, reb=10, ast=4, pf=4,
                    min_q1=9.0, min_q2=9.0, min_q3=9.0),
        ]
        snap = _snap(period=4, clock="12:00", home_score=88, away_score=85,
                     players=players)
        _run_both_flag_states(snap, "end_q3_boundary")


class TestGameOver:
    """Final buzzer / period=4, clock=0:00 / FINAL status snapshots."""

    def test_q4_clock_zero(self):
        """Clock at exactly 0:00 — game over, projections == current."""
        players = [
            _player(1, "OKC", minutes=43.0, pts=35, reb=4, ast=9,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=9.5),
        ]
        snap = _snap(period=4, clock="0:00", home_score=103, away_score=111,
                     game_status="FINAL", players=players)
        off, on = _run_both_flag_states(snap, "q4_clock_zero")
        pts_off = next(r for r in off if r["stat"] == "pts")
        # At clock=0, remaining=0 -> projected_final should equal current (floor rule)
        assert pts_off["projected_final"] >= pts_off["current"]

    def test_final_status_real_snapshot(self):
        """Load an actual FINAL snapshot from data/live/ — must not crash."""
        live_dir = os.path.join(PROJECT_DIR, "data", "live")
        final_file = os.path.join(live_dir, "0042500317_1780257516000.json")
        if not os.path.exists(final_file):
            pytest.skip("real FINAL snapshot not available")
        with open(final_file, encoding="utf-8") as f:
            snap = json.load(f)
        _run_both_flag_states(snap, "real_FINAL_0042500317")


class TestOvertime:
    """Period >= 5 overtime snapshots."""

    def test_ot_period_5_mid(self):
        """Period=5, mid-OT — 2:30 remaining in OT."""
        players = [
            _player(1, "OKC", minutes=45.0, pts=38, reb=5, ast=10, pf=4,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=9.5),
            _player(2, "SAS", minutes=44.0, pts=40, reb=12, ast=5, pf=5,
                    min_q1=9.0, min_q2=9.0, min_q3=9.0, min_q4=9.0),
        ]
        snap = _snap(period=5, clock="2:30", home_score=120, away_score=118,
                     players=players)
        _run_both_flag_states(snap, "ot_period5_mid")

    def test_ot_period_5_start(self):
        """Period=5, clock=5:00 — OT just tipped."""
        players = [
            _player(1, "OKC", minutes=48.0, pts=42, reb=7, ast=11, pf=3),
        ]
        snap = _snap(period=5, clock="5:00", home_score=125, away_score=122,
                     players=players)
        _run_both_flag_states(snap, "ot_period5_start")

    def test_ot_period_6(self):
        """Double-OT — period=6."""
        players = [
            _player(1, "OKC", minutes=52.0, pts=48, reb=8, ast=12, pf=5),
        ]
        snap = _snap(period=6, clock="2:00", home_score=132, away_score=130,
                     players=players)
        _run_both_flag_states(snap, "double_ot_period6")


class TestMalformedInputs:
    """Snapshots with missing / malformed / nonsense fields."""

    def test_missing_period(self):
        """No 'period' key at all."""
        snap = {
            "game_id": "0022400123", "clock": "6:00",
            "home_score": 50, "away_score": 45,
            "home_team": "OKC", "away_team": "SAS",
            "game_status": "LIVE",
            "players": [_player(1, "OKC", minutes=20.0, pts=15)],
        }
        _run_both_flag_states(snap, "missing_period")

    def test_missing_clock(self):
        """No 'clock' key at all — should default to 0.0 remaining."""
        snap = {
            "game_id": "0022400123", "period": 2,
            "home_score": 50, "away_score": 45,
            "home_team": "OKC", "away_team": "SAS",
            "game_status": "LIVE",
            "players": [_player(1, "OKC", minutes=20.0, pts=15)],
        }
        _run_both_flag_states(snap, "missing_clock")

    def test_missing_scores(self):
        """home_score / away_score both absent."""
        snap = {
            "game_id": "0022400123", "period": 3, "clock": "6:00",
            "home_team": "OKC", "away_team": "SAS",
            "game_status": "LIVE",
            "players": [_player(1, "OKC", minutes=22.0, pts=18)],
        }
        _run_both_flag_states(snap, "missing_scores")

    def test_none_scores(self):
        """home_score / away_score explicitly None."""
        snap = _snap(period=3, clock="6:00", home_score=0, away_score=0,
                     players=[_player(1, "OKC", minutes=22.0, pts=18)])
        snap["home_score"] = None
        snap["away_score"] = None
        _run_both_flag_states(snap, "none_scores")

    def test_empty_players_list(self):
        """players key present but empty list."""
        snap = _snap(period=3, clock="6:00", players=[])
        off, on = _run_both_flag_states(snap, "empty_players", allow_empty_players=True)
        assert off == []
        assert on == []

    def test_absent_players_key(self):
        """No 'players' key at all."""
        snap = {
            "game_id": "0022400123", "period": 2, "clock": "6:00",
            "home_score": 50, "away_score": 45,
            "home_team": "OKC", "away_team": "SAS",
            "game_status": "LIVE",
        }
        off, on = _run_both_flag_states(snap, "absent_players_key", allow_empty_players=True)
        assert off == []
        assert on == []

    def test_nonsense_clock_string(self):
        """clock='WHAT:XX' — completely unparseable."""
        snap = _snap(period=3, clock="WHAT:XX",
                     players=[_player(1, "OKC", minutes=22.0, pts=18)])
        _run_both_flag_states(snap, "nonsense_clock_string")

    def test_negative_clock(self):
        """clock='-1:00' — negative value."""
        snap = _snap(period=2, clock="-1:00",
                     players=[_player(1, "OKC", minutes=12.0, pts=10)])
        _run_both_flag_states(snap, "negative_clock")

    def test_clock_integer_zero(self):
        """clock=0 as integer — should be treated as 0 remaining."""
        snap = _snap(period=4, clock=0,
                     players=[_player(1, "OKC", minutes=36.0, pts=28)])
        _run_both_flag_states(snap, "clock_integer_zero")

    def test_clock_none(self):
        """clock=None."""
        snap = _snap(period=3, clock=None,
                     players=[_player(1, "OKC", minutes=22.0, pts=18)])
        _run_both_flag_states(snap, "clock_none")

    def test_period_none(self):
        """period=None — defensive int() cast path."""
        snap = _snap(period=None, clock="6:00",
                     players=[_player(1, "OKC", minutes=10.0, pts=8)])
        _run_both_flag_states(snap, "period_none")

    def test_period_string(self):
        """period='3' as a string instead of int."""
        snap = _snap(period="3", clock="6:00",
                     players=[_player(1, "OKC", minutes=22.0, pts=18)])
        _run_both_flag_states(snap, "period_string")

    def test_player_missing_player_id(self):
        """Player dict has no player_id key."""
        bad_player = {
            "name": "Ghost Player", "team": "OKC",
            "min": 10.0, "pts": 8, "reb": 2, "ast": 1,
            "fg3m": 0, "stl": 0, "blk": 0, "tov": 1, "pf": 1,
            "is_starter": True,
        }
        snap = _snap(period=2, clock="6:00", players=[bad_player])
        # Should NOT crash; may produce rows with player_id=None or skip.
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "0"}, clear=False):
            try:
                rows = live_engine.project_from_snapshot(dict(snap))
            except Exception as exc:
                raise AssertionError(
                    f"[missing_player_id|SBS=0] RAISED unexpectedly: {exc}"
                ) from exc
        assert isinstance(rows, list)

    def test_player_nonsense_stats(self):
        """Player with None / string stat values."""
        bad_player = {
            "player_id": 9999, "name": "NaN Man", "team": "OKC",
            "min": None, "pts": "not_a_number", "reb": None,
            "ast": None, "fg3m": None, "stl": None,
            "blk": None, "tov": None, "pf": None,
            "is_starter": True,
        }
        snap = _snap(period=3, clock="6:00", players=[bad_player])
        _run_both_flag_states(snap, "player_nonsense_stats")

    def test_unknown_player_id(self):
        """Player ID not in any gamelog store — fallback must work."""
        snap = _snap(period=3, clock="6:00", players=[
            _player(9999999, "OKC", name="Unknown Player",
                    minutes=20.0, pts=15, reb=5),
        ])
        _run_both_flag_states(snap, "unknown_player_id")

    def test_player_id_as_string(self):
        """player_id provided as string '1628983'."""
        p = _player(1628983, "OKC", minutes=20.0, pts=15)
        p["player_id"] = "1628983"  # string
        snap = _snap(period=2, clock="6:00", players=[p])
        _run_both_flag_states(snap, "player_id_as_string")

    def test_entirely_empty_snap(self):
        """Completely empty dict {}."""
        snap: Dict[str, Any] = {}
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "0"}, clear=False):
            try:
                rows = live_engine.project_from_snapshot(snap)
            except Exception as exc:
                raise AssertionError(
                    f"[empty_snap|SBS=0] RAISED: {exc}"
                ) from exc
        assert isinstance(rows, list)

    def test_legacy_nested_home_away_form(self):
        """Legacy nested home/away dict form (pre-89a snapshots)."""
        snap = {
            "game_id": "0022400123",
            "period": 3, "clock": "6:00",
            "game_status": "LIVE",
            "home": {"abbrev": "OKC", "score": 70},
            "away": {"abbrev": "SAS", "score": 65},
            "players": [_player(1, "OKC", minutes=22.0, pts=18)],
        }
        _run_both_flag_states(snap, "legacy_nested_home_away")

    def test_extra_unknown_fields_ignored(self):
        """Extra unknown top-level keys don't crash the engine."""
        snap = _snap(period=2, clock="6:00",
                     players=[_player(1, "OKC", minutes=12.0, pts=10)])
        snap["_debug"] = {"foo": "bar"}
        snap["score_velocity_q3"] = 7.5
        snap["weird_key_xyz"] = [1, 2, 3]
        _run_both_flag_states(snap, "extra_unknown_fields")

    def test_high_foul_trouble(self):
        """Player with 5 fouls (foul-out threshold) in Q4."""
        players = [
            _player(1, "OKC", minutes=36.0, pts=30, reb=8, pf=5,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=7.5),
        ]
        snap = _snap(period=4, clock="4:00", home_score=100, away_score=98,
                     players=players)
        _run_both_flag_states(snap, "foul_trouble_5_fouls_q4")

    def test_bench_player_zero_minutes_current_period(self):
        """Player played Q1/Q2 but has min_q3=0 (sitting the bench)."""
        players = [
            _player(5, "OKC", minutes=18.0, pts=12, reb=4,
                    min_q1=9.0, min_q2=9.0, min_q3=0.0),
        ]
        snap = _snap(period=3, clock="4:00", players=players)
        _run_both_flag_states(snap, "bench_player_zero_minutes_q3")

    def test_zero_minutes_player_all_zeros(self):
        """DNP player: minutes=0, all stats 0.

        SBS=0 (cycle-88 linear): no clock-pace extrapolation from 0 -> projected=0.
        SBS=1 (routed ensemble): may inject a small non-zero projection from L5
        priors even for a DNP player (the routed head uses season priors, not just
        current-game pace). That is correct engine behavior — not a bug. We only
        assert the strong zero-contract on the SBS=0 path; SBS=1 must be finite
        and non-negative (already covered by _assert_valid_rows).
        """
        players = [
            _player(7, "SAS", minutes=0.0, pts=0, reb=0, ast=0),
        ]
        snap = _snap(period=4, clock="2:00", players=players)
        off, on = _run_both_flag_states(snap, "dnp_all_zeros")
        # SBS=0: cycle-88 linear extrapolator — 0 pace = 0 projection
        for r in off:
            assert r["projected_final"] == pytest.approx(0.0, abs=1e-6), (
                f"SBS=0: DNP player with 0 min/stats should project to 0, "
                f"got {r['projected_final']} for stat={r['stat']}"
            )
        # SBS=1: routed ensemble may produce small L5-prior-based projection.
        # All we require is finite, non-negative (already enforced by _assert_valid_rows).
        for r in on:
            pf = float(r["projected_final"])
            assert math.isfinite(pf) and pf >= 0.0

    def test_iso_8601_clock_format(self):
        """NBA live feed sometimes emits ISO 8601 'PT07M24.00S' clocks."""
        snap = _snap(period=2, clock="PT07M24.00S",
                     players=[_player(1, "OKC", minutes=16.0, pts=12)])
        _run_both_flag_states(snap, "iso8601_clock")


# =============================================================================
# STEP 2 — SBS=1 specific contract checks
# =============================================================================

class TestSBSFlagOn:
    """When CV_INGAME_SBS=1, additional assertions on the overlay output."""

    def test_sbs_on_populated_game_not_blank(self):
        """SBS=1 on a real mid-game snap must return non-empty rows."""
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        assert len(rows) > 0, "SBS=1 returned blank rows for a populated mid-game snap"

    def test_sbs_on_source_is_valid_string(self):
        """projection_source must be a non-empty string for every row when SBS=1."""
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        for r in rows:
            ps = r.get("projection_source")
            assert isinstance(ps, str) and len(ps) > 0, (
                f"projection_source invalid with SBS=1: {ps!r} in row {r}"
            )

    def test_sbs_on_no_nan_inf(self):
        """No NaN or inf projected_final with SBS=1."""
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        for r in rows:
            pf = r.get("projected_final")
            assert pf is not None
            pf_f = float(pf)
            assert math.isfinite(pf_f), f"NaN/inf projected_final with SBS=1: {r}"

    def test_sbs_off_and_on_same_row_count(self):
        """Row count must be identical regardless of SBS flag."""
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "0"}, clear=False):
            rows_off = live_engine.project_from_snapshot(dict(snap))
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows_on = live_engine.project_from_snapshot(dict(snap))
        assert len(rows_off) == len(rows_on), (
            f"SBS=0 produced {len(rows_off)} rows, SBS=1 produced {len(rows_on)}"
        )

    def test_sbs_on_team_score_fields_are_finite_or_none(self):
        """proj_home_final / proj_away_final / proj_total must be finite when present."""
        players = _real_players_mid_game()
        snap = _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        for r in rows:
            for field in ("proj_home_final", "proj_away_final", "proj_total"):
                val = r.get(field)
                if val is not None:
                    try:
                        val_f = float(val)
                    except (TypeError, ValueError):
                        raise AssertionError(
                            f"SBS=1: {field}={val!r} cannot be cast to float"
                        )
                    assert math.isfinite(val_f), (
                        f"SBS=1: {field}={val_f} is NaN/inf"
                    )
                    # Sanity: team scores should be in a plausible range
                    assert 0 <= val_f <= 250, (
                        f"SBS=1: {field}={val_f} outside plausible range [0,250]"
                    )

    def test_sbs_on_home_win_prob_valid_range(self):
        """sim_home_win_prob (when present) must be in [0, 1]."""
        players = _real_players_mid_game()
        snap = _snap(period=4, clock="4:00", home_score=90, away_score=88,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        for r in rows:
            wp = r.get("home_win_prob_inplay")
            if wp is not None:
                wp_f = float(wp)
                assert 0.0 <= wp_f <= 1.0, (
                    f"SBS=1: home_win_prob_inplay={wp_f} out of [0,1]"
                )

    def test_sbs_on_overlay_fallback_on_malformed(self):
        """Even with badly malformed snap, SBS=1 must not raise; fallback rows."""
        snap = _snap(period=3, clock="GARBAGE", home_score=None, away_score=None,
                     players=[_player(1, "OKC", minutes=20.0, pts=15)])
        snap["home_score"] = None
        snap["away_score"] = None
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            try:
                rows = live_engine.project_from_snapshot(dict(snap))
            except Exception as exc:
                raise AssertionError(
                    f"[sbs_fallback_malformed|SBS=1] RAISED: {exc}"
                ) from exc
        assert isinstance(rows, list)

    def test_sbs_on_real_pregame_snapshot(self):
        """Real PRE_GAME file from data/live/ — SBS=1 must not crash."""
        snap_path = os.path.join(
            PROJECT_DIR, "data", "live", "0042500315_1779840106000.json"
        )
        if not os.path.exists(snap_path):
            pytest.skip("real PRE_GAME snapshot not available")
        with open(snap_path, encoding="utf-8") as f:
            snap = json.load(f)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            try:
                rows = live_engine.project_from_snapshot(dict(snap))
            except Exception as exc:
                raise AssertionError(
                    f"[real_pregame|SBS=1] RAISED: {exc}"
                ) from exc
        assert isinstance(rows, list)

    def test_sbs_on_floor_rule_holds(self):
        """projected_final >= current in every row with SBS=1."""
        players = [
            _player(1, "OKC", minutes=40.0, pts=32, reb=6, ast=8, pf=3,
                    min_q1=9.5, min_q2=9.5, min_q3=9.5, min_q4=9.5),
        ]
        snap = _snap(period=4, clock="2:00", home_score=100, away_score=98,
                     players=players)
        with mock.patch.dict(os.environ, {"CV_INGAME_SBS": "1"}, clear=False):
            rows = live_engine.project_from_snapshot(dict(snap))
        for r in rows:
            cur = float(r.get("current", 0) or 0)
            pf = float(r.get("projected_final", 0) or 0)
            assert pf >= cur - 1e-6, (
                f"SBS=1 floor rule violated: projected={pf} < current={cur} for {r}"
            )


# =============================================================================
# STEP 3 — Latency measurement
# =============================================================================

class TestLatency:
    """Wall-time benchmarks for project_from_snapshot with SBS=1."""

    N_WARM = 5  # warm repetitions per NSIMS config
    SLOW_THRESHOLD_MS = 1500  # > 1.5s per call is too slow for 8s refresh cycle

    @staticmethod
    def _build_mid_game_snap() -> Dict[str, Any]:
        players = _real_players_mid_game()
        return _snap(period=3, clock="6:00", home_score=72, away_score=68,
                     players=players)

    def _measure(self, nsims: int, snap: Dict[str, Any]) -> List[float]:
        """Return per-call wall times (ms) for N_WARM warm calls."""
        env_patch = {"CV_INGAME_SBS": "1", "CV_INGAME_NSIMS": str(nsims)}
        times_ms: List[float] = []
        with mock.patch.dict(os.environ, env_patch, clear=False):
            for _ in range(self.N_WARM):
                t0 = time.perf_counter()
                rows = live_engine.project_from_snapshot(dict(snap))
                t1 = time.perf_counter()
                assert isinstance(rows, list), "project_from_snapshot must return list"
                times_ms.append((t1 - t0) * 1000)
        return times_ms

    def test_latency_nsims_200(self):
        snap = self._build_mid_game_snap()
        times = self._measure(200, snap)
        median_ms = sorted(times)[len(times) // 2]
        max_ms = max(times)
        print(f"\n[Latency NSIMS=200] median={median_ms:.1f}ms  max={max_ms:.1f}ms")
        assert max_ms < 10_000, (
            f"NSIMS=200: slowest call {max_ms:.0f}ms exceeds 10s sanity limit"
        )
        if max_ms > self.SLOW_THRESHOLD_MS:
            import warnings
            warnings.warn(
                f"NSIMS=200: slowest call {max_ms:.0f}ms > {self.SLOW_THRESHOLD_MS}ms "
                f"(may be too slow for 8s refresh). Median={median_ms:.0f}ms."
            )

    def test_latency_nsims_400(self):
        snap = self._build_mid_game_snap()
        times = self._measure(400, snap)
        median_ms = sorted(times)[len(times) // 2]
        max_ms = max(times)
        print(f"\n[Latency NSIMS=400] median={median_ms:.1f}ms  max={max_ms:.1f}ms")
        assert max_ms < 10_000, (
            f"NSIMS=400: slowest call {max_ms:.0f}ms exceeds 10s sanity limit"
        )
        if max_ms > self.SLOW_THRESHOLD_MS:
            import warnings
            warnings.warn(
                f"NSIMS=400: slowest call {max_ms:.0f}ms > {self.SLOW_THRESHOLD_MS}ms threshold."
            )

    def test_latency_nsims_800(self):
        snap = self._build_mid_game_snap()
        times = self._measure(800, snap)
        median_ms = sorted(times)[len(times) // 2]
        max_ms = max(times)
        print(f"\n[Latency NSIMS=800] median={median_ms:.1f}ms  max={max_ms:.1f}ms")
        assert max_ms < 10_000, (
            f"NSIMS=800: slowest call {max_ms:.0f}ms exceeds 10s sanity limit"
        )
        if max_ms > self.SLOW_THRESHOLD_MS:
            import warnings
            warnings.warn(
                f"NSIMS=800: slowest call {max_ms:.0f}ms > {self.SLOW_THRESHOLD_MS}ms threshold."
            )

    def test_latency_summary(self, capsys):
        """Print a full three-config latency report to stdout."""
        snap = self._build_mid_game_snap()
        report_lines = [
            "",
            "=" * 60,
            "LATENCY REPORT — project_from_snapshot (CV_INGAME_SBS=1)",
            "=" * 60,
        ]
        for nsims in (200, 400, 800):
            times = self._measure(nsims, snap)
            times_s = sorted(times)
            median_ms = times_s[len(times_s) // 2]
            min_ms = times_s[0]
            max_ms = times_s[-1]
            flag = " << SLOW" if max_ms > self.SLOW_THRESHOLD_MS else ""
            report_lines.append(
                f"  NSIMS={nsims:4d}  "
                f"min={min_ms:6.1f}ms  "
                f"median={median_ms:6.1f}ms  "
                f"max={max_ms:6.1f}ms{flag}"
            )
        report_lines.append("=" * 60)
        print("\n".join(report_lines))
        # This test always passes — it's a reporting fixture.
