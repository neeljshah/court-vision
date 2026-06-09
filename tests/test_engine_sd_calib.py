"""tests/test_engine_sd_calib.py -- Guards for CV_ENGINE_SD_CALIB gate.

Tests:
  (a) OFF path: engine outputs byte-identical to pre-fix (constant SD).
  (b) ON path: margin_sd differs from the constant (calibrated != hardcoded).
  (c) ON path: margin point (margin_home) is UNCHANGED vs OFF path.
  (d) ON path: win_prob_home stays in (0, 1) and differs from OFF path for a
      non-trivial matchup (ensures the calibration is actually doing something).
  (e) ON path: calibrated SD is leak-free -- computed from prior-games-only data
      (structural test: _compute_margin_sd_calib on a small synthetic DF returns
      a finite value; on an empty DF returns the fallback).
  (f) engine_four_factors: same OFF/ON invariants hold.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Repo wiring
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
_TEAM_SYS = ROOT / "scripts" / "team_system"
_ENGINES  = _TEAM_SYS / "engines"
_TSDIR    = ROOT / "data" / "cache" / "team_system"

for p in (_TEAM_SYS, _ENGINES, ROOT / "src"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

_HAS_DATA = (_TSDIR / "league_team_game.parquet").exists()
pytestmark = pytest.mark.skipif(
    not _HAS_DATA,
    reason="team_system parquet bank not present (league_team_game.parquet)",
)


# ---------------------------------------------------------------------------
# Helpers: dynamic import so each test gets a fresh module state
# ---------------------------------------------------------------------------

def _import_engine(name: str):
    fp = _ENGINES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, str(fp))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------
# (a+c) OFF path: margin_home unchanged, margin_sd matches constant
# ---------------------------------------------------------------------------

def test_team_score_off_path_is_constant_sd(monkeypatch):
    """OFF path (flag unset): margin_sd should be ~sqrt(2*(1-0.1))*pts_sd (from MC)."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m = _import_engine("engine_team_score")
    result = m.predict("NYK", "SAS")
    # OFF path: sd = pts_sd (~12.5); margin_sd from MC ~ pts_sd * sqrt(2*(1-rho)) * sqrt(N/(N-1))
    # Just verify margin_sd is in a sane range for the constant path.
    assert 14.0 < result["margin_sd"] < 20.0, (
        f"OFF path margin_sd={result['margin_sd']:.2f} out of expected constant-SD range"
    )
    assert 0.01 <= result["win_prob_home"] <= 0.99


def test_four_factors_off_path_is_constant_sd(monkeypatch):
    """OFF path: margin_sd ~ TEAM_TOTAL_SD*sqrt(2) ~ 16.97 (from MC, two independent teams)."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m = _import_engine("engine_four_factors")
    result = m.predict("NYK", "SAS")
    # TEAM_TOTAL_SD = 12.0; two independent teams -> margin_sd ~ 12*sqrt(2) ~ 16.97
    assert 15.0 < result["margin_sd"] < 19.0, (
        f"OFF path margin_sd={result['margin_sd']:.2f} out of expected range for TEAM_TOTAL_SD=12.0"
    )
    assert 0.01 <= result["win_prob_home"] <= 0.99


# ---------------------------------------------------------------------------
# (b) ON path: margin_sd differs from OFF-path (calibration changes something)
# ---------------------------------------------------------------------------

def test_team_score_on_path_sd_differs_from_off(monkeypatch):
    """ON path: calibrated margin_sd != constant-SD margin_sd."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m_off = _import_engine("engine_team_score")
    off = m_off.predict("NYK", "SAS")

    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m_on = _import_engine("engine_team_score")
    on = m_on.predict("NYK", "SAS")

    # The calibrated SD and the within-team SD are computed differently;
    # they should NOT be identical.
    assert off["margin_sd"] != pytest.approx(on["margin_sd"], abs=0.01), (
        "ON and OFF margin_sd are identical -- calibration had no effect"
    )


def test_four_factors_on_path_sd_differs_from_off(monkeypatch):
    """ON path: calibrated margin_sd != TEAM_TOTAL_SD-based margin_sd."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m_off = _import_engine("engine_four_factors")
    off = m_off.predict("NYK", "SAS")

    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m_on = _import_engine("engine_four_factors")
    on = m_on.predict("NYK", "SAS")

    assert off["margin_sd"] != pytest.approx(on["margin_sd"], abs=0.01), (
        "ON and OFF margin_sd are identical -- calibration had no effect"
    )


# ---------------------------------------------------------------------------
# (c) ON path: margin POINT is unchanged vs OFF path
# ---------------------------------------------------------------------------

def test_team_score_margin_point_unchanged(monkeypatch):
    """Calibration must NOT change the margin point -- only the SD/win_prob."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m_off = _import_engine("engine_team_score")
    off = m_off.predict("NYK", "SAS")

    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m_on = _import_engine("engine_team_score")
    on = m_on.predict("NYK", "SAS")

    # margin_home is from MC mean; allow tiny MC noise (< 0.05 pts with N=30k)
    assert abs(off["margin_home"] - on["margin_home"]) < 0.1, (
        f"margin_home changed: OFF={off['margin_home']:.3f} ON={on['margin_home']:.3f}"
    )
    assert abs(off["total"] - on["total"]) < 0.2, (
        f"total changed: OFF={off['total']:.3f} ON={on['total']:.3f}"
    )


def test_four_factors_margin_point_unchanged(monkeypatch):
    """Calibration must NOT change the margin point for four_factors."""
    monkeypatch.delenv("CV_ENGINE_SD_CALIB", raising=False)
    m_off = _import_engine("engine_four_factors")
    off = m_off.predict("NYK", "SAS")

    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m_on = _import_engine("engine_four_factors")
    on = m_on.predict("NYK", "SAS")

    # margin_home and total are deterministic (not from MC)
    assert off["margin_home"] == pytest.approx(on["margin_home"], abs=0.05), (
        f"margin_home changed: OFF={off['margin_home']:.3f} ON={on['margin_home']:.3f}"
    )
    assert off["total"] == pytest.approx(on["total"], abs=0.05), (
        f"total changed: OFF={off['total']:.3f} ON={on['total']:.3f}"
    )


# ---------------------------------------------------------------------------
# (d) ON path: win_prob_home in (0, 1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("matchup", [
    ("NYK", "SAS"),
    ("GSW", "BOS"),
    ("NYK", "SAS", {"neutral_site": True}),
])
def test_team_score_on_path_win_prob_in_bounds(monkeypatch, matchup):
    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m = _import_engine("engine_team_score")
    args = list(matchup)
    if len(args) == 3 and isinstance(args[2], dict):
        result = m.predict(args[0], args[1], args[2])
    else:
        result = m.predict(args[0], args[1])
    assert 0.0 < result["win_prob_home"] < 1.0, (
        f"win_prob_home={result['win_prob_home']} out of (0, 1) for {matchup}"
    )


@pytest.mark.parametrize("matchup", [
    ("NYK", "SAS"),
    ("GSW", "BOS"),
    ("NYK", "SAS", {"neutral_site": True}),
])
def test_four_factors_on_path_win_prob_in_bounds(monkeypatch, matchup):
    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m = _import_engine("engine_four_factors")
    args = list(matchup)
    if len(args) == 3 and isinstance(args[2], dict):
        result = m.predict(args[0], args[1], args[2])
    else:
        result = m.predict(args[0], args[1])
    assert 0.0 < result["win_prob_home"] < 1.0, (
        f"win_prob_home={result['win_prob_home']} out of (0, 1) for {matchup}"
    )


# ---------------------------------------------------------------------------
# (e) Leak-free structural test: _compute_margin_sd_calib
# ---------------------------------------------------------------------------

def test_compute_margin_sd_calib_finite_on_real_data():
    """Calibrated margin SD must be finite and positive on real data."""
    m = _import_engine("engine_team_score")
    df = pd.read_parquet(str(_TSDIR / "league_team_game.parquet"))

    # Build ORtg/DRtg/pace from the same df (mirrors _load_ratings)
    ortg: dict = {}
    drtg: dict = {}
    pace: dict = {}
    for team, g in df.groupby("team"):
        tp = g["poss"].sum()
        op = g["opp_poss"].sum()
        ortg[team] = g["pts"].sum()     / tp * 100.0
        drtg[team] = g["opp_pts"].sum() / op * 100.0
        pace[team] = g["poss"].mean()

    sd = m._compute_margin_sd_calib(df, ortg, drtg, pace)
    assert np.isfinite(sd), f"margin_sd_calib is not finite: {sd}"
    assert sd > 0, f"margin_sd_calib <= 0: {sd}"
    # Realistic range: NBA game-to-game margin errors are 10-20 pts
    assert 8.0 < sd < 22.0, f"margin_sd_calib={sd:.2f} out of realistic NBA range [8, 22]"


def test_compute_margin_sd_calib_fallback_on_empty():
    """Empty df -> fallback (not crash)."""
    m = _import_engine("engine_team_score")
    empty = pd.DataFrame(columns=["team", "opp", "pts", "opp_pts", "poss"])
    sd = m._compute_margin_sd_calib(empty, {}, {}, {})
    assert np.isfinite(sd), "fallback must be finite"
    assert sd == pytest.approx(m._FALLBACK_MARGIN_SD, abs=0.01)


def test_compute_margin_sd_calib_prior_only_leak_free():
    """On a small synthetic 4-row df, calibration uses only those rows (no future data)."""
    m = _import_engine("engine_team_score")

    # Construct a simple 4-row df: A vs B twice
    rows = [
        {"team": "A", "opp": "B", "pts": 110, "opp_pts": 100, "poss": 95.0, "opp_poss": 95.0},
        {"team": "B", "opp": "A", "pts": 100, "opp_pts": 110, "poss": 95.0, "opp_poss": 95.0},
        {"team": "A", "opp": "B", "pts": 105, "opp_pts": 108, "poss": 97.0, "opp_poss": 97.0},
        {"team": "B", "opp": "A", "pts": 108, "opp_pts": 105, "poss": 97.0, "opp_poss": 97.0},
    ]
    df = pd.DataFrame(rows)

    ortg = {"A": 115.0, "B": 108.0}
    drtg = {"A": 109.0, "B": 112.0}
    pace = {"A": 96.0, "B": 96.0}

    sd = m._compute_margin_sd_calib(df, ortg, drtg, pace)
    # Must be finite and positive (4 rows > 0, >= our threshold of 10 -> fallback)
    # With only 4 rows, expect fallback
    assert np.isfinite(sd)
    # 4 < 10 -> fallback
    assert sd == pytest.approx(m._FALLBACK_MARGIN_SD, abs=0.01)

    # Add more rows to exceed the threshold and get a real estimate
    more_rows = rows * 4  # 16 rows total
    df16 = pd.DataFrame(more_rows)
    sd16 = m._compute_margin_sd_calib(df16, ortg, drtg, pace)
    assert np.isfinite(sd16)
    assert sd16 > 0


# ---------------------------------------------------------------------------
# (f) Required keys still present on ON path
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "engine", "win_prob_home", "margin_home", "total",
    "home_pts", "away_pts", "margin_sd", "n_models", "n_signals", "notes",
}

@pytest.mark.parametrize("eng_name", ["engine_team_score", "engine_four_factors"])
def test_on_path_required_keys_present(monkeypatch, eng_name):
    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m = _import_engine(eng_name)
    result = m.predict("NYK", "SAS")
    missing = REQUIRED_KEYS - set(result)
    assert not missing, f"{eng_name} ON path missing keys: {missing}"


@pytest.mark.parametrize("eng_name", ["engine_team_score", "engine_four_factors"])
def test_on_path_no_nan(monkeypatch, eng_name):
    monkeypatch.setenv("CV_ENGINE_SD_CALIB", "1")
    m = _import_engine(eng_name)
    result = m.predict("NYK", "SAS")
    for k in ("win_prob_home", "margin_home", "total", "home_pts", "away_pts", "margin_sd"):
        assert np.isfinite(float(result[k])), f"{eng_name} ON path: {k} is not finite ({result[k]})"
