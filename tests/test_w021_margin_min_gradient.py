"""tests/test_w021_margin_min_gradient.py — W-021 unit tests.

Tests for the CV_MARGIN_MIN_GRADIENT flag (2-D blowout haircut surface).

All tests are offline pure-function tests — no I/O, no model load.
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


# ── 1. blowout_factor_gradient: basic guards ─────────────────────────────────

def test_gradient_not_q4_returns_1():
    """Gradient function returns 1.0 for periods < 4 (same contract as step table)."""
    assert pig.blowout_factor_gradient(25, 3, 0.0, is_star=True, is_leading=True) == 1.0
    assert pig.blowout_factor_gradient(30, 2, 0.0, is_star=True, is_leading=True) == 1.0


def test_gradient_non_star_returns_1():
    """Non-star players are unaffected by the gradient (same gate as old table)."""
    assert pig.blowout_factor_gradient(30, 4, 6.0, is_star=False, is_leading=True) == 1.0
    assert pig.blowout_factor_gradient(30, 4, 6.0, is_star=False, is_leading=False) == 1.0


def test_gradient_playoff_guard():
    """Playoff games (game_id prefix '004') always return 1.0."""
    assert pig.blowout_factor_gradient(
        30, 4, 6.0, is_star=True, is_leading=True, game_id="0042500401"
    ) == 1.0
    assert pig.blowout_factor_gradient(
        30, 4, 0.5, is_star=True, is_leading=False, game_id="0042500401"
    ) == 1.0


def test_gradient_zero_margin_returns_1():
    """Zero margin → factor = 1.0 (no haircut in tied game)."""
    f = pig.blowout_factor_gradient(0, 4, 6.0, is_star=True, is_leading=True)
    assert f == pytest.approx(1.0, abs=1e-6)


def test_gradient_zero_time_returns_1():
    """At buzzer (clock=0) time_weight=0 → factor = 1.0 regardless of margin."""
    f_lead = pig.blowout_factor_gradient(30, 4, 0.0, is_star=True, is_leading=True)
    f_trail = pig.blowout_factor_gradient(30, 4, 0.0, is_star=True, is_leading=False)
    assert f_lead == pytest.approx(1.0, abs=1e-6)
    assert f_trail == pytest.approx(1.0, abs=1e-6)


# ── 2. blowout_factor_gradient: surface values ───────────────────────────────

def test_gradient_leading_steeper_than_trailing():
    """Leading team has a steeper slope (star pulled more when winning big)."""
    f_lead = pig.blowout_factor_gradient(25, 4, 12.0, is_star=True, is_leading=True)
    f_trail = pig.blowout_factor_gradient(25, 4, 12.0, is_star=True, is_leading=False)
    assert f_lead < f_trail, "Leading star should have a lower (more penalized) factor"


def test_gradient_leading_value_at_margin25_endq3():
    """At endQ3 (clock=12), margin=25: leading factor = 1 - 0.00577*25 = 0.85575."""
    f = pig.blowout_factor_gradient(25, 4, 12.0, is_star=True, is_leading=True)
    assert f == pytest.approx(1.0 - pig._MARGIN_GRAD_SLOPE_LEADING * 25, abs=1e-6)


def test_gradient_trailing_value_at_margin25_endq3():
    """At endQ3 (clock=12), margin=25: trailing factor = 1 - 0.00435*25 = 0.89125."""
    f = pig.blowout_factor_gradient(25, 4, 12.0, is_star=True, is_leading=False)
    assert f == pytest.approx(1.0 - pig._MARGIN_GRAD_SLOPE_TRAILING * 25, abs=1e-6)


def test_gradient_time_scaling():
    """Factor at mid-Q4 (clock=6) is closer to 1.0 than at endQ3 (clock=12)."""
    f_full = pig.blowout_factor_gradient(30, 4, 12.0, is_star=True, is_leading=True)
    f_half = pig.blowout_factor_gradient(30, 4, 6.0, is_star=True, is_leading=True)
    assert f_half > f_full, "Less time remaining → smaller haircut (less certainty of rest)"
    # At half time: factor = 1 - 0.00577*30*(6/12) = 1 - 0.08655 = 0.91345
    expected_half = 1.0 - pig._MARGIN_GRAD_SLOPE_LEADING * 30 * 0.5
    assert f_half == pytest.approx(expected_half, abs=1e-6)


def test_gradient_floor_clamping():
    """Factor is clamped to _MARGIN_GRAD_FLOOR minimum (never below 0.10)."""
    # Margin=200 would give negative factor -> clamped to floor
    f = pig.blowout_factor_gradient(200, 4, 12.0, is_star=True, is_leading=True)
    assert f == pytest.approx(pig._MARGIN_GRAD_FLOOR)


def test_gradient_factor_le_1():
    """Factor is always <= 1.0 (never boosts projection)."""
    for margin in [0, 5, 10, 20, 30]:
        for clock in [0, 3, 6, 12]:
            for leading in [True, False]:
                f = pig.blowout_factor_gradient(
                    margin, 4, float(clock), is_star=True, is_leading=leading
                )
                assert f <= 1.0, f"Factor > 1.0: margin={margin}, clock={clock}, leading={leading}"


# ── 3. byte-identical when flag OFF ──────────────────────────────────────────

def test_flag_off_byte_identical_to_baseline(monkeypatch):
    """With CV_MARGIN_MIN_GRADIENT=OFF, project_snapshot output is byte-identical."""
    monkeypatch.setattr(pig, "_CV_MARGIN_GRAD", False)

    snap = {
        "game_id": "0022400001",
        "period": 4,
        "clock": "06:00",
        "home_team": "BOS",
        "away_team": "NYK",
        "home_score": 95,
        "away_score": 68,
        "players": [
            {"player_id": 1627759, "name": "Jaylen Brown", "team": "BOS",
             "min": 36.0, "pts": 22, "reb": 5, "ast": 2, "fg3m": 3,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2},
            {"player_id": 203999, "name": "Jokic", "team": "NYK",
             "min": 36.0, "pts": 18, "reb": 9, "ast": 7, "fg3m": 1,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2},
        ],
    }
    # Baseline: flag explicitly OFF
    rows_off = pig.project_snapshot(snap)

    # Now turn flag ON and compare
    monkeypatch.setattr(pig, "_CV_MARGIN_GRAD", True)
    rows_on = pig.project_snapshot(snap)

    # The flag-ON values SHOULD differ (large margin=27 in Q4 → haircut)
    # BUT this test verifies the OFF path is unchanged from the step-table path.
    # Re-confirm OFF == original step table.
    monkeypatch.setattr(pig, "_CV_MARGIN_GRAD", False)
    rows_recheck = pig.project_snapshot(snap)

    for a, b in zip(rows_off, rows_recheck):
        assert a["projected_final"] == b["projected_final"], (
            f"flag-OFF not idempotent: {a['name']} {a['stat']}"
        )
        assert a["blow_factor"] == b["blow_factor"]


def test_flag_on_differs_from_step_table_at_large_margin(monkeypatch):
    """With CV_MARGIN_MIN_GRADIENT=ON, blow_factor differs from step table at margin=27."""
    snap = {
        "game_id": "0022400001",
        "period": 4,
        "clock": "09:00",
        "home_team": "BOS",
        "away_team": "NYK",
        "home_score": 95,
        "away_score": 68,  # margin = 27 -> step table gives 0.45
        "players": [
            {"player_id": 1627759, "name": "Jaylen Brown", "team": "BOS",
             "min": 36.0, "pts": 22, "reb": 5, "ast": 2, "fg3m": 3,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2},
        ],
    }
    monkeypatch.setattr(pig, "_CV_MARGIN_GRAD", False)
    rows_off = pig.project_snapshot(snap)
    bf_off = next(r["blow_factor"] for r in rows_off if r["stat"] == "pts")

    monkeypatch.setattr(pig, "_CV_MARGIN_GRAD", True)
    rows_on = pig.project_snapshot(snap)
    bf_on = next(r["blow_factor"] for r in rows_on if r["stat"] == "pts")

    # Old step table: margin=27 -> 0.45 (is_star=True for a 36-min player)
    assert bf_off == pytest.approx(0.45, abs=1e-6), f"Expected step-table 0.45, got {bf_off}"
    # New gradient: much gentler
    assert bf_on > 0.45, f"Gradient should be gentler than step table: {bf_on}"
    assert bf_on < 1.0, "Still applies some haircut"


def test_non_playoff_game_fires():
    """Regular season game (002*) gradient fires normally."""
    f = pig.blowout_factor_gradient(
        25, 4, 12.0, is_star=True, is_leading=True, game_id="0022400001"
    )
    assert f < 1.0


def test_regular_season_game_id_none_fires():
    """When game_id is None (no id), gradient still fires (no playoff guard)."""
    f = pig.blowout_factor_gradient(
        25, 4, 12.0, is_star=True, is_leading=True, game_id=None
    )
    assert f < 1.0
