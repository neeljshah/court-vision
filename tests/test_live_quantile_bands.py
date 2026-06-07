"""tests/test_live_quantile_bands.py -- Cycle 105c (loop 5).

Six regression tests for the in-play q10/q50/q90 band layer:

  1. project_from_snapshot_with_bands returns rows with q10/q50/q90 fields
  2. q10 <= q50 <= q90 always (monotonicity)
  3. q50 matches the point projection exactly (no point change)
  4. Synthetic Gaussian residuals -> calibrator achieves ~80% coverage
  5. Asymmetric branch (fg3m/stl/blk/tov) floors q10 at 0
  6. Back-compat: missing calibration artifact -> wide-open bands

FIX IN-4 tests (7, 8):
  7. endQ3 extra_mult is forced to 1.0 even when per-player cal artifact
     is present and game_date/pid are supplied (safe guard).
  8. endQ1/endQ2 modulation path is NOT disabled (unchanged behaviour).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import live_quantile_bands as lqb  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_snap(period: int = 4) -> dict:
    """Minimal canonical snapshot with one player who's played 36 mins of Q1-Q3."""
    return {
        "game_id": "TEST_001",
        "period": period,
        "clock": "12:00",
        "home_team": "BOS",
        "away_team": "LAL",
        "home_score": 90.0,
        "away_score": 85.0,
        "players": [
            {
                "player_id": 1, "name": "Test Player", "team": "BOS",
                "min": 27.0,
                "pts": 18.0, "reb": 6.0, "ast": 4.0, "fg3m": 2.0,
                "stl": 1.0, "blk": 0.0, "tov": 2.0, "pf": 2.0,
                "min_q1": 9.0, "min_q2": 9.0, "min_q3": 9.0, "min_q4": 0.0,
            },
        ],
    }


def _stub_calibration(tmpdir: str) -> str:
    """Write a stub calibration JSON and return its path. Used to exercise the
    band path without actually fitting against the retro."""
    payload = {
        "endQ2": {
            "pts": {"sigma": 4.0, "scale": 1.0, "asymmetric": False},
            "reb": {"sigma": 1.8, "scale": 1.0, "asymmetric": False},
            "ast": {"sigma": 1.3, "scale": 1.0, "asymmetric": False},
            "fg3m": {"sigma": 0.9, "scale": 1.2, "asymmetric": True},
            "stl": {"sigma": 0.7, "scale": 1.2, "asymmetric": True},
            "blk": {"sigma": 0.5, "scale": 1.2, "asymmetric": True},
            "tov": {"sigma": 0.8, "scale": 1.2, "asymmetric": True},
        },
        "endQ3": {
            "pts": {"sigma": 3.5, "scale": 1.0, "asymmetric": False},
            "reb": {"sigma": 1.6, "scale": 1.0, "asymmetric": False},
            "ast": {"sigma": 1.2, "scale": 1.0, "asymmetric": False},
            "fg3m": {"sigma": 0.8, "scale": 1.2, "asymmetric": True},
            "stl": {"sigma": 0.6, "scale": 1.2, "asymmetric": True},
            "blk": {"sigma": 0.4, "scale": 1.2, "asymmetric": True},
            "tov": {"sigma": 0.7, "scale": 1.2, "asymmetric": True},
        },
    }
    p = os.path.join(tmpdir, "live_quantile_calibration.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return p


# ── 1. fields are present ─────────────────────────────────────────────────────

def test_bands_for_fields_present():
    cal = {"endQ3": {"pts": {"sigma": 3.0, "scale": 1.0, "asymmetric": False}}}
    b = lqb.bands_for("pts", 20.0, "endQ3", calibration=cal)
    assert set(b.keys()) == {"q10", "q50", "q90"}


# ── 2. monotonicity ───────────────────────────────────────────────────────────

def test_bands_monotonic():
    cal = {
        "endQ3": {
            "pts": {"sigma": 3.0, "scale": 1.0, "asymmetric": False},
            "blk": {"sigma": 0.4, "scale": 1.5, "asymmetric": True},
        }
    }
    for stat, q50 in [("pts", 25.0), ("pts", 0.5), ("blk", 1.0), ("blk", 0.0)]:
        b = lqb.bands_for(stat, q50, "endQ3", calibration=cal)
        assert b["q10"] <= b["q50"] <= b["q90"], (
            f"monotonicity failure stat={stat} q50={q50} bands={b}"
        )


# ── 3. q50 unchanged ──────────────────────────────────────────────────────────

def test_q50_matches_point_projection():
    cal = {"endQ3": {"pts": {"sigma": 3.0, "scale": 1.0, "asymmetric": False}}}
    for q50 in (0.0, 12.5, 25.0, 50.0):
        b = lqb.bands_for("pts", q50, "endQ3", calibration=cal)
        assert b["q50"] == q50


# ── 4. synthetic Gaussian residuals -> 80% coverage ───────────────────────────

def test_synthetic_gaussian_calibration_hits_80pct():
    """Cycle-40 pattern: scale=1.0 against a true Gaussian gives exactly the
    standard-normal 80% interval (z=1.2816). Coverage must hit ~80%."""
    rng = np.random.RandomState(42)
    n = 5000
    sigma = 3.5
    projections = np.full(n, 20.0)
    residuals = rng.normal(0.0, sigma, n)
    actuals = projections + residuals
    cal = {"endQ3": {"pts": {"sigma": sigma, "scale": 1.0,
                             "asymmetric": False}}}
    covered = 0
    for p, a in zip(projections, actuals):
        b = lqb.bands_for("pts", float(p), "endQ3", calibration=cal)
        if b["q10"] <= a <= b["q90"]:
            covered += 1
    cov = covered / n
    assert 0.77 <= cov <= 0.83, f"expected ~0.80 coverage, got {cov:.3f}"


# ── 5. asymmetric branch floors at 0 ──────────────────────────────────────────

def test_asymmetric_floor_at_zero():
    """For skewed counts (FG3M/STL/BLK/TOV) with low q50, q10 must clamp to 0
    rather than going negative."""
    cal = {
        "endQ3": {
            stat: {"sigma": 1.5, "scale": 1.5, "asymmetric": True}
            for stat in ("fg3m", "stl", "blk", "tov")
        }
    }
    for stat in ("fg3m", "stl", "blk", "tov"):
        # q50=0.5 with sigma*scale*z = 1.5*1.5*1.2816 ~= 2.88 would give
        # q10 = -2.38 in the symmetric branch; asymmetric must floor at 0.
        b = lqb.bands_for(stat, 0.5, "endQ3", calibration=cal)
        assert b["q10"] >= 0.0, f"{stat}: q10={b['q10']} should be floored at 0"
        assert b["q90"] > b["q50"], f"{stat}: q90 must exceed q50"


# ── 6. back-compat: missing artifact -> wide-open ─────────────────────────────

def test_missing_calibration_wide_open():
    """No cal entry -> q10=0, q90=2*q50. Mirrors cycle-40 back-compat."""
    # Empty calibration dict, no entry for endQ3/pts.
    b = lqb.bands_for("pts", 20.0, "endQ3", calibration={})
    assert b["q10"] == 0.0
    assert b["q50"] == 20.0
    assert b["q90"] == 40.0

    # Unsupported snapshot point (endQ1) -> wide-open even with cal present.
    cal = {"endQ3": {"pts": {"sigma": 3.0, "scale": 1.0, "asymmetric": False}}}
    b1 = lqb.bands_for("pts", 10.0, None, calibration=cal)
    assert b1["q10"] == 0.0 and b1["q90"] == 20.0


# ── bonus: end-to-end through project_from_snapshot_with_bands ────────────────

def test_project_with_bands_attaches_fields():
    """project_from_snapshot_with_bands must return rows carrying all three
    band keys, with q50 == projected_final exactly (no point change)."""
    with tempfile.TemporaryDirectory() as tmp:
        cal_path = _stub_calibration(tmp)
        lqb.reset_cache()
        snap = _fake_snap(period=4)
        rows = lqb.project_from_snapshot_with_bands(
            snap, calibration_path=cal_path)
        assert rows, "expected non-empty projection rows"
        for r in rows:
            assert "q10" in r and "q50" in r and "q90" in r
            assert r["q10"] <= r["q50"] <= r["q90"]
            assert r["q50"] == float(r.get("projected_final") or 0.0)
        lqb.reset_cache()


# ── 7. FIX IN-4: endQ3 extra_mult is always 1.0 ──────────────────────────────

def test_endQ3_extra_mult_is_one_with_pp_cal(tmp_path):
    """FIX IN-4 (safe variant): bands_for at endQ3 must return the same bands
    regardless of whether pid/game_date + a per-player calibration artifact are
    supplied.  The extra_mult guard must force 1.0 for endQ3, preventing the
    ~1.342 over-coverage caused by a missing/default pop_mean_std."""
    lqb.reset_cache()

    cal = {
        "endQ3": {
            "pts": {"sigma": 3.5, "scale": 1.0, "asymmetric": False},
            "reb": {"sigma": 1.6, "scale": 1.0, "asymmetric": False},
        }
    }

    # Reference bands: legacy path (no pid / game_date -> extra_mult=1.0).
    ref_pts = lqb.bands_for("pts", 20.0, "endQ3", calibration=cal)
    ref_reb = lqb.bands_for("reb",  6.0, "endQ3", calibration=cal)

    # Inject a V2 per-player calibration artifact that deliberately omits
    # per_stat_rescale/pop_mean_std for endQ3 (simulating the real broken
    # state where pop_std defaults to 1.0 and ratio saturates to 1.8).
    pp_v2 = {
        "endQ1": {
            "per_stat_rescale": {"pts": 0.99, "reb": 0.98},
            "pop_mean_std":     {"pts": 5.66, "reb": 2.31},
        },
        "endQ2": {
            "per_stat_rescale": {"pts": 0.96, "reb": 0.97},
            "pop_mean_std":     {"pts": 5.66, "reb": 2.31},
        },
        # endQ3 intentionally absent / missing pop_mean_std (real bug scenario).
    }
    pp_path = tmp_path / "per_player_quantile_calibration_v2.json"
    pp_path.write_text(json.dumps(pp_v2), encoding="utf-8")

    # Monkeypatch the V2 path so the loader finds our stub.
    orig_path = lqb._PP_CAL_PATH_V2
    lqb._PP_CAL_PATH_V2 = str(pp_path)
    lqb.reset_cache()  # clear loader cache after path swap

    try:
        # Supply a pid + game_date that would normally trigger per-player mod.
        modulated_pts = lqb.bands_for(
            "pts", 20.0, "endQ3", calibration=cal,
            pid=2544, game_date="2026-04-01",
        )
        modulated_reb = lqb.bands_for(
            "reb", 6.0, "endQ3", calibration=cal,
            pid=2544, game_date="2026-04-01",
        )
    finally:
        lqb._PP_CAL_PATH_V2 = orig_path
        lqb.reset_cache()

    # endQ3 bands must be IDENTICAL whether or not the per-player path fires.
    assert modulated_pts["q10"] == ref_pts["q10"], (
        f"endQ3 pts q10 changed: {modulated_pts['q10']} != {ref_pts['q10']}"
    )
    assert modulated_pts["q90"] == ref_pts["q90"], (
        f"endQ3 pts q90 changed: {modulated_pts['q90']} != {ref_pts['q90']}"
    )
    assert modulated_reb["q10"] == ref_reb["q10"], (
        f"endQ3 reb q10 changed: {modulated_reb['q10']} != {ref_reb['q10']}"
    )
    assert modulated_reb["q90"] == ref_reb["q90"], (
        f"endQ3 reb q90 changed: {modulated_reb['q90']} != {ref_reb['q90']}"
    )


# ── 8. FIX IN-4: endQ1/endQ2 modulation path still fires ────────────────────

def test_endQ1_endQ2_modulation_not_disabled(tmp_path):
    """FIX IN-4: the endQ3 guard must NOT touch endQ1 or endQ2 modulation.
    When a V2 per-player artifact with full endQ1/endQ2 buckets is present AND
    a real gamelog entry provides std_l20, the modulated bands must differ from
    the unmodulated bands (proving the elif path is still reachable)."""
    lqb.reset_cache()

    cal = {
        "endQ1": {
            "pts": {"sigma": 5.0, "scale": 1.0, "asymmetric": False},
        },
        "endQ2": {
            "pts": {"sigma": 4.5, "scale": 1.0, "asymmetric": False},
        },
    }

    # Reference: no pid/game_date -> extra_mult=1.0.
    ref_q1 = lqb.bands_for("pts", 20.0, "endQ1", calibration=cal)
    ref_q2 = lqb.bands_for("pts", 20.0, "endQ2", calibration=cal)

    # Inject V2 artifact WITH endQ1/endQ2 buckets.
    pp_v2 = {
        "endQ1": {
            "per_stat_rescale": {"pts": 0.99},
            "pop_mean_std":     {"pts": 5.0},   # pop_std == sigma -> ratio matters
        },
        "endQ2": {
            "per_stat_rescale": {"pts": 0.98},
            "pop_mean_std":     {"pts": 5.0},
        },
    }
    pp_path = tmp_path / "per_player_quantile_calibration_v2.json"
    pp_path.write_text(json.dumps(pp_v2), encoding="utf-8")

    # Inject a gamelog entry so std_l20 returns a non-pop value (std != pop_std).
    # We use pid=99999 with 10 identical games (std=0) -> ratio clips to 0.6 ->
    # extra_mult = rescale * sqrt(0.6) < 1.0 -> NARROWER bands than reference.
    gamelog_entries = [
        {"GAME_DATE": f"Jan {i:02d}, 2026", "PTS": 20, "REB": 6, "AST": 4,
         "FG3M": 2, "STL": 1, "BLK": 0, "TOV": 2}
        for i in range(1, 11)
    ]
    gl_path = tmp_path / "gamelog_99999.json"
    gl_path.write_text(json.dumps(gamelog_entries), encoding="utf-8")

    orig_pp_path = lqb._PP_CAL_PATH_V2
    orig_gl_glob = lqb._GAMELOG_GLOB
    lqb._PP_CAL_PATH_V2 = str(pp_path)
    lqb._GAMELOG_GLOB = str(tmp_path / "gamelog_*.json")
    lqb.reset_cache()

    try:
        mod_q1 = lqb.bands_for(
            "pts", 20.0, "endQ1", calibration=cal,
            pid=99999, game_date="2026-02-01",
        )
        mod_q2 = lqb.bands_for(
            "pts", 20.0, "endQ2", calibration=cal,
            pid=99999, game_date="2026-02-01",
        )
    finally:
        lqb._PP_CAL_PATH_V2 = orig_pp_path
        lqb._GAMELOG_GLOB = orig_gl_glob
        lqb.reset_cache()

    # With std_l20=0 -> ratio clips to 0.6 -> extra_mult < 1 -> bands narrower.
    # The point here is simply that the bands CHANGED (modulation fired).
    assert mod_q1["q90"] != ref_q1["q90"], (
        "endQ1 per-player modulation should fire but bands were unchanged; "
        f"mod={mod_q1} ref={ref_q1}"
    )
    assert mod_q2["q90"] != ref_q2["q90"], (
        "endQ2 per-player modulation should fire but bands were unchanged; "
        f"mod={mod_q2} ref={ref_q2}"
    )
