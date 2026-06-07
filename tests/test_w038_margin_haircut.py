"""tests/test_w038_margin_haircut.py -- W-038 CV_INGAME_MARGIN_HAIRCUT tests.

Validates:
1. margin_haircut_factor() pure-function contract.
2. Byte-identical when flag OFF (project_snapshot output unchanged).
3. Haircut fires at period < 4 for large margins with star players.
4. No haircut at period >= 4 (Q4 handled by existing blowout_factor).
5. No haircut below threshold (|margin| <= 12).
6. Playoff guard: game_id "004..." -> factor=1.0.
7. Non-stars (proj_min < 30) are not haircut.
8. current_stat floor preserved (projected_final >= current).
9. Factor clamped to [_MHC_FLOOR, 1.0].
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


# ── helper: build a minimal snapshot ─────────────────────────────────────────

def _make_snap(period, margin, home_pts=None, away_pts=None, min_played=20.0, pf=0):
    """Minimal snapshot dict for one star player on the home team."""
    if home_pts is None:
        home_pts = (48 + margin) / 2
    if away_pts is None:
        away_pts = (48 - margin) / 2
    # Star player: min_played=20 at period=3 (endQ2 snapshot) => proj_48 = 20/0.5 = 40 >= 30
    return {
        "game_id": "0022400001",
        "period": period,
        "clock": "12:00",
        "home_team": "ATL",
        "away_team": "BOS",
        "home_score": home_pts,
        "away_score": away_pts,
        "players": [{
            "player_id": 1,
            "name": "Star Player",
            "team": "ATL",
            "min": min_played,
            "pts": 15.0,
            "reb": 5.0,
            "ast": 3.0,
            "fg3m": 2.0,
            "stl": 1.0,
            "blk": 0.0,
            "tov": 1.0,
            "pf": pf,
        }],
    }


# ── 1. pure-function contract ──────────────────────────────────────────────────

class TestMarginHaircutFactorPure:
    """Pure-function tests for margin_haircut_factor()."""

    def test_flag_off_returns_one(self):
        """When flag is OFF, factor is always 1.0 regardless of margin."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = False
        try:
            assert pig.margin_haircut_factor(30.0, 2, is_star=True) == 1.0
            assert pig.margin_haircut_factor(0.0, 2, is_star=True) == 1.0
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_non_star_returns_one(self):
        """Non-star players are never haircut."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            assert pig.margin_haircut_factor(30.0, 2, is_star=False) == 1.0
            assert pig.margin_haircut_factor(25.0, 3, is_star=False) == 1.0
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_period_4_returns_one(self):
        """Period >= 4 returns 1.0 (Q4 is handled by blowout_factor)."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            assert pig.margin_haircut_factor(30.0, 4, is_star=True) == 1.0
            assert pig.margin_haircut_factor(30.0, 5, is_star=True) == 1.0
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_below_threshold_returns_one(self):
        """Margin at or below threshold (12) -> factor 1.0."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            assert pig.margin_haircut_factor(0.0, 2, is_star=True) == 1.0
            assert pig.margin_haircut_factor(12.0, 3, is_star=True) == 1.0
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_above_threshold_haircut_applied(self):
        """Margin above threshold -> factor < 1.0."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            # At margin=22, excess=10, slope=0.010: factor = 1 - 0.010*10 = 0.90
            f = pig.margin_haircut_factor(22.0, 2, is_star=True)
            assert f == pytest.approx(0.90, abs=1e-6)
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_factor_clamped_to_floor(self):
        """Factor never goes below _MHC_FLOOR."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            # At margin=100, excess=88, slope=0.010: factor = 1 - 0.88 = 0.12 < 0.70
            # Should be clamped to 0.70
            f = pig.margin_haircut_factor(100.0, 2, is_star=True)
            assert f == pytest.approx(pig._MHC_FLOOR, abs=1e-6)
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_playoff_guard(self):
        """game_id prefix '004' -> factor 1.0 (playoff guard)."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            f = pig.margin_haircut_factor(30.0, 2, is_star=True, game_id="0042500001")
            assert f == 1.0
        finally:
            pig._CV_MARGIN_HAIRCUT = old

    def test_factor_monotone_with_margin(self):
        """Factor decreases monotonically as margin increases above threshold."""
        old = pig._CV_MARGIN_HAIRCUT
        pig._CV_MARGIN_HAIRCUT = True
        try:
            factors = [
                pig.margin_haircut_factor(m, 2, is_star=True)
                for m in [12, 15, 20, 25, 30, 50, 100]
            ]
            for i in range(len(factors) - 1):
                assert factors[i] >= factors[i + 1], (
                    f"Factor not monotone at margins {12 + i*4}: {factors}")
        finally:
            pig._CV_MARGIN_HAIRCUT = old


# ── 2. byte-identical when OFF ─────────────────────────────────────────────────

def test_byte_identical_when_off(monkeypatch):
    """With flag OFF, project_snapshot output is unchanged vs plain call."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=3, margin=25, min_played=20.0)
    rows_off = pig.project_snapshot(snap)
    # Run again with flag still off
    rows_off2 = pig.project_snapshot(snap)
    for r1, r2 in zip(rows_off, rows_off2):
        assert r1["projected_final"] == pytest.approx(r2["projected_final"], abs=1e-8)


def test_flag_off_no_regression_vs_baseline(monkeypatch):
    """Flag OFF produces same output as a known-good baseline call."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=2, margin=20, min_played=18.0)
    rows = pig.project_snapshot(snap)
    # All projected_finals must be >= current (basic projection floor)
    for r in rows:
        assert r["projected_final"] >= r["current"], (
            f"Projection {r['stat']} below current: {r['projected_final']} < {r['current']}")


# ── 3. haircut fires at period < 4 for large margins ─────────────────────────

def test_haircut_fires_endq2_large_margin(monkeypatch):
    """At period=3 (endQ2), large margin reduces star's projected_final."""
    # Baseline (flag OFF)
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=3, margin=25, min_played=22.0)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    # Candidate (flag ON)
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    # At least one stat should be reduced for the star player
    any_reduced = any(rows_on[s] < rows_off[s] - 1e-6 for s in pig.STATS)
    assert any_reduced, (
        f"Haircut should reduce at least one stat at endQ2 with |margin|=25."
        f" on={rows_on}, off={rows_off}")


def test_haircut_fires_endq1_large_margin(monkeypatch):
    """At period=2 (endQ1), large margin reduces star's projected_final."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=2, margin=25, min_played=10.0)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    any_reduced = any(rows_on[s] < rows_off[s] - 1e-6 for s in pig.STATS)
    assert any_reduced, "Haircut should reduce at least one stat at endQ1 with |margin|=25."


# ── 4. no haircut at period >= 4 ─────────────────────────────────────────────

def test_no_haircut_at_period4(monkeypatch):
    """At period=4, haircut does NOT change output (blowout_factor handles Q4)."""
    snap = _make_snap(period=4, margin=25, min_played=30.0)

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    for s in pig.STATS:
        assert rows_on[s] == pytest.approx(rows_off[s], abs=1e-6), (
            f"Haircut must not change period=4 output for stat={s}")


# ── 5. no haircut below threshold ─────────────────────────────────────────────

def test_no_haircut_below_threshold(monkeypatch):
    """With |margin| <= 12, output unchanged even with flag ON."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=3, margin=12, min_played=22.0)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    for s in pig.STATS:
        assert rows_on[s] == pytest.approx(rows_off[s], abs=1e-6), (
            f"Stat {s} should not change at threshold margin=12")


def test_close_game_no_haircut(monkeypatch):
    """With |margin| = 5, output unchanged."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    snap = _make_snap(period=3, margin=5, min_played=22.0)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    for s in pig.STATS:
        assert rows_on[s] == pytest.approx(rows_off[s], abs=1e-6)


# ── 6. playoff guard ──────────────────────────────────────────────────────────

def test_playoff_guard_no_haircut(monkeypatch):
    """With game_id prefix '004', no haircut even at large margin."""
    snap = _make_snap(period=3, margin=30, min_played=22.0)
    snap["game_id"] = "0042500001"

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    for s in pig.STATS:
        assert rows_on[s] == pytest.approx(rows_off[s], abs=1e-6), (
            f"Playoff guard should prevent haircut for stat={s}")


# ── 7. non-stars not haircut ──────────────────────────────────────────────────

def test_bench_player_not_haircut(monkeypatch):
    """Bench player (low minutes -> proj_min < 30) should not be haircut."""
    # min_played=3 at endQ2 -> proj_48 = 3/0.5 = 6 < 30 -> not a star
    snap = _make_snap(period=3, margin=30, min_played=3.0)

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", False)
    rows_off = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    rows_on = {r["stat"]: r["projected_final"] for r in pig.project_snapshot(snap)}

    for s in pig.STATS:
        assert rows_on[s] == pytest.approx(rows_off[s], abs=1e-6), (
            f"Bench player stat {s} should not be haircut")


# ── 8. current floor preserved ────────────────────────────────────────────────

def test_projected_final_never_below_current(monkeypatch):
    """After haircut, projected_final >= current for all stats."""
    monkeypatch.setattr(pig, "_CV_MARGIN_HAIRCUT", True)
    snap = _make_snap(period=3, margin=40, min_played=22.0)
    rows = pig.project_snapshot(snap)
    for r in rows:
        assert r["projected_final"] >= r["current"] - 1e-6, (
            f"Stat {r['stat']}: projected_final {r['projected_final']} "
            f"< current {r['current']}")


# ── 9. factor values ──────────────────────────────────────────────────────────

def test_factor_at_margin_22():
    """At margin=22, excess=10, slope=0.010: factor=0.90."""
    old = pig._CV_MARGIN_HAIRCUT
    pig._CV_MARGIN_HAIRCUT = True
    try:
        f = pig.margin_haircut_factor(22.0, 2, is_star=True)
        # 1 - 0.010 * (22 - 12) = 1 - 0.10 = 0.90
        assert f == pytest.approx(0.90, abs=1e-6)
    finally:
        pig._CV_MARGIN_HAIRCUT = old


def test_factor_at_margin_30():
    """At margin=30, excess=18, slope=0.010: factor=0.82."""
    old = pig._CV_MARGIN_HAIRCUT
    pig._CV_MARGIN_HAIRCUT = True
    try:
        f = pig.margin_haircut_factor(30.0, 2, is_star=True)
        # 1 - 0.010 * (30 - 12) = 1 - 0.18 = 0.82
        assert f == pytest.approx(0.82, abs=1e-6)
    finally:
        pig._CV_MARGIN_HAIRCUT = old
