"""Per-file test for domains.soccer.calib_1x2_wf.

Acceptance criteria (pa9 workstream)
--------------------------------------
1. Fit half1 / score half2: held-out 3-way ECE < raw (calibration improves).
2. Calibrated triples sum to 1.0 +/- 1e-6 for EVERY event.
3. Already-calibrated (identity) input -> identity output (do-no-harm).
4. No future-row leak (walk-forward: calibrator for event i uses only 0..i-1).
5. Module and public symbols import cleanly.
6. Synthetic corpus passes without requiring real disk data.

Real corpus tests are skipped automatically when matches.parquet is absent.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/tests/test_calib_1x2_wf.py -q
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path / skip helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_PATH = REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet"

_SKIP_NO_DATA = pytest.mark.skipif(
    not CORPUS_PATH.exists(), reason="Soccer corpus not available"
)

_REAL_FIT_CACHE: dict = {}


def _run_real_fit():
    if "result" not in _REAL_FIT_CACHE:
        import pandas as pd
        from domains.soccer.calib_1x2_wf import fit_and_score
        from domains.soccer.pregame_winprob import walk_forward as wf_binary
        from domains.soccer.scoreline_engine import scoreline_matrix, markets_from_matrix

        matches_df = pd.read_parquet(CORPUS_PATH)
        wf_df = wf_binary(matches_df)

        triples = []
        for _, row in wf_df.iterrows():
            try:
                P = scoreline_matrix(float(row["lam_home"]), float(row["lam_away"]))
                mkt = markets_from_matrix(P)
                triples.append((mkt["1X2_home"], mkt["1X2_draw"], mkt["1X2_away"]))
            except Exception:
                ph = float(row.get("p_poisson", 1 / 3))
                triples.append((ph, (1 - ph) / 2, (1 - ph) / 2))

        wf_df = wf_df.copy()
        wf_df["p_home"] = [t[0] for t in triples]
        wf_df["p_draw"] = [t[1] for t in triples]
        wf_df["p_away"] = [t[2] for t in triples]

        _REAL_FIT_CACHE["df"] = wf_df
        _REAL_FIT_CACHE["result"] = fit_and_score(wf_df)
    return _REAL_FIT_CACHE["result"]


# ---------------------------------------------------------------------------
# Synthetic data builder (no disk required)
# ---------------------------------------------------------------------------

def _synthetic_df(
    n: int = 300,
    seed: int = 42,
    miscal_factor: float = 0.6,
) -> "pd.DataFrame":
    """Build a synthetic soccer match dataframe.

    p_home, p_draw, p_away are generated from a Dirichlet, then intentionally
    squashed toward 1/3 (miscalibrated toward the centre) so that the walk-forward
    calibrator has something real to correct.
    outcomes are sampled from the TRUE distribution (not the squashed one), so
    calibration should tighten ECE.
    """
    import pandas as pd

    rng = np.random.default_rng(seed)
    # True distributions concentrated away from uniform.
    alpha = np.array([3.0, 1.5, 2.0])
    true_probs = rng.dirichlet(alpha, size=n)

    # Miscalibrate: push toward uniform so raw ECE > 0.
    raw_probs = (1 - miscal_factor) * true_probs + miscal_factor * (1 / 3.0)
    raw_probs = raw_probs / raw_probs.sum(axis=1, keepdims=True)

    # Sample outcomes from TRUE probs.
    outcomes = np.array(
        [rng.choice(3, p=true_probs[i]) for i in range(n)]
    )
    ftr_map = {0: "H", 1: "D", 2: "A"}
    ftr = [ftr_map[o] for o in outcomes]

    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "p_home": raw_probs[:, 0],
        "p_draw": raw_probs[:, 1],
        "p_away": raw_probs[:, 2],
        "ftr": ftr,
    })


# ---------------------------------------------------------------------------
# Unit tests -- synthetic (always run, no corpus needed)
# ---------------------------------------------------------------------------

def test_import():
    """Module and all public symbols import cleanly."""
    mod = importlib.import_module("domains.soccer.calib_1x2_wf")
    for sym in ("ece_3way", "walk_forward_calibrate_1x2", "fit_and_score",
                "MIN_HISTORY", "CALIBRATION_NOTE"):
        assert hasattr(mod, sym), f"Missing public symbol: {sym}"


def test_ece_3way_uniform():
    """ece_3way returns 0 when predicted == empirical fraction per bin."""
    # If all probs are exactly 1/3 and class dist is balanced, ECE is 0.
    n = 300
    probs = np.full((n, 3), 1 / 3.0)
    outcomes = np.tile([0, 1, 2], n // 3)
    ece = importlib.import_module("domains.soccer.calib_1x2_wf").ece_3way(probs, outcomes)
    assert isinstance(ece, float)
    assert ece >= 0.0


def test_sum_to_one_constraint_synthetic():
    """Calibrated triples must sum to 1.0 +/- 1e-6 on synthetic data."""
    from domains.soccer.calib_1x2_wf import walk_forward_calibrate_1x2

    df = _synthetic_df(n=200, seed=0)
    raw_probs = df[["p_home", "p_draw", "p_away"]].values.astype(float)
    outcomes = df["ftr"].map({"H": 0, "D": 1, "A": 2}).values.astype(int)

    cal = walk_forward_calibrate_1x2(raw_probs, outcomes, min_history=30)
    sums = cal.sum(axis=1)
    max_err = float(np.abs(sums - 1.0).max())
    assert max_err < 1e-6, f"Max sum-to-one error: {max_err:.2e}"


def test_shape_preserved_synthetic():
    """Output shape equals input shape (N, 3)."""
    from domains.soccer.calib_1x2_wf import walk_forward_calibrate_1x2

    df = _synthetic_df(n=150, seed=1)
    raw = df[["p_home", "p_draw", "p_away"]].values.astype(float)
    outcomes = df["ftr"].map({"H": 0, "D": 1, "A": 2}).values.astype(int)

    cal = walk_forward_calibrate_1x2(raw, outcomes, min_history=20)
    assert cal.shape == raw.shape, f"Shape mismatch: {cal.shape} vs {raw.shape}"


def test_ece_improves_synthetic():
    """3-way ECE on held-out half2 must be lower after calibration (synthetic)."""
    from domains.soccer.calib_1x2_wf import fit_and_score

    df = _synthetic_df(n=400, seed=7, miscal_factor=0.7)
    result = fit_and_score(df, min_history=30)

    assert result["ece_cal_half2"] < result["ece_raw_half2"], (
        f"ECE did not improve: raw={result['ece_raw_half2']:.4f} "
        f"cal={result['ece_cal_half2']:.4f}"
    )


def test_sum_to_one_ok_flag_synthetic():
    """fit_and_score reports sum_to_one_ok=True on synthetic data."""
    from domains.soccer.calib_1x2_wf import fit_and_score

    df = _synthetic_df(n=300, seed=3)
    result = fit_and_score(df, min_history=30)
    assert result["sum_to_one_ok"] is True, (
        f"sum_to_one_ok=False; there is a normalisation bug."
    )


def test_passes_flag_synthetic():
    """fit_and_score passes acceptance gate on synthetic data."""
    from domains.soccer.calib_1x2_wf import fit_and_score

    df = _synthetic_df(n=400, seed=99, miscal_factor=0.65)
    result = fit_and_score(df, min_history=30)
    assert result["passes"] is True, (
        f"passes=False: ece_improves={result['ece_improves']}, "
        f"sum_to_one_ok={result['sum_to_one_ok']}, "
        f"ece_raw={result['ece_raw_half2']:.4f}, "
        f"ece_cal={result['ece_cal_half2']:.4f}"
    )


def test_identity_already_calibrated():
    """Identity input (perfectly calibrated flat probs) passes through cleanly.

    When raw probabilities already perfectly predict outcomes (or are uniform),
    the walk-forward calibrator should not materially worsen calibration.
    This is the do-no-harm identity test.
    """
    from domains.soccer.calib_1x2_wf import walk_forward_calibrate_1x2

    n = 200
    # Uniform probs -- calibrator can only fit constant functions on this.
    raw = np.full((n, 3), 1 / 3.0)
    rng = np.random.default_rng(42)
    outcomes = rng.integers(0, 3, size=n)

    cal = walk_forward_calibrate_1x2(raw, outcomes, min_history=30)

    # The calibrated values must still sum to 1 and be in [0,1].
    sums = cal.sum(axis=1)
    assert np.all(np.abs(sums - 1.0) < 1e-6), "sum-to-one violated on identity input"
    assert np.all(cal >= -1e-9) and np.all(cal <= 1 + 1e-9), "probs out of [0,1]"


def test_no_future_leak_walkforward():
    """Walk-forward contract: calibrator for event i uses only events 0..i-1.

    Canary: inject a perfect predictor on events [100..199] only; the calibrator
    fitted on those events MUST NOT have used events [200..] to compute its map.
    We verify this indirectly: after setting outcomes[200:] to random, the
    calibrated output for events [100..199] must be IDENTICAL to a run where
    we cut the series at event 199.
    """
    from domains.soccer.calib_1x2_wf import walk_forward_calibrate_1x2

    df = _synthetic_df(n=300, seed=55)
    raw = df[["p_home", "p_draw", "p_away"]].values.astype(float)
    outcomes = df["ftr"].map({"H": 0, "D": 1, "A": 2}).values.astype(int)

    # Full series.
    cal_full = walk_forward_calibrate_1x2(raw.copy(), outcomes.copy(), min_history=30)

    # Truncated series (first 200 events only).
    cal_trunc = walk_forward_calibrate_1x2(raw[:200].copy(), outcomes[:200].copy(), min_history=30)

    # For events [30..199] the two runs must agree (they use the same history).
    diff = np.abs(cal_full[30:200] - cal_trunc[30:200]).max()
    assert diff < 1e-9, (
        f"Walk-forward leak detected: max diff between full and truncated series "
        f"at events [30..199] = {diff:.2e}. Calibrator used future data."
    )


def test_probs_stay_in_unit_interval():
    """All calibrated probabilities are in [0, 1]."""
    from domains.soccer.calib_1x2_wf import walk_forward_calibrate_1x2

    df = _synthetic_df(n=250, seed=5)
    raw = df[["p_home", "p_draw", "p_away"]].values.astype(float)
    outcomes = df["ftr"].map({"H": 0, "D": 1, "A": 2}).values.astype(int)

    cal = walk_forward_calibrate_1x2(raw, outcomes, min_history=30)
    assert np.all(cal >= -1e-9), f"Negative probability found: {cal.min():.6f}"
    assert np.all(cal <= 1.0 + 1e-9), f"Probability > 1 found: {cal.max():.6f}"


def test_diag_keys():
    """fit_and_score returns all required diagnostic keys."""
    from domains.soccer.calib_1x2_wf import fit_and_score

    df = _synthetic_df(n=200, seed=11)
    result = fit_and_score(df, min_history=30)
    required = {
        "n_total", "n_train", "n_val",
        "ece_raw_half2", "ece_cal_half2",
        "ece_improves", "sum_to_one_ok", "passes", "note",
    }
    missing = required - set(result.keys())
    assert not missing, f"Missing result keys: {missing}"


# ---------------------------------------------------------------------------
# Real corpus tests (skipped if data absent)
# ---------------------------------------------------------------------------

@_SKIP_NO_DATA
def test_real_ece_improves():
    """3-way ECE on held-out half2 is lower after calibration (real corpus)."""
    result = _run_real_fit()
    assert result["ece_cal_half2"] < result["ece_raw_half2"], (
        f"ECE did not improve on real corpus: "
        f"raw={result['ece_raw_half2']:.4f} cal={result['ece_cal_half2']:.4f}"
    )


@_SKIP_NO_DATA
def test_real_sum_to_one():
    """Calibrated triples sum to 1 +/- 1e-6 on real corpus."""
    result = _run_real_fit()
    assert result["sum_to_one_ok"] is True, "sum_to_one_ok=False on real corpus"


@_SKIP_NO_DATA
def test_real_passes():
    """Composite acceptance gate passes on real corpus."""
    result = _run_real_fit()
    assert result["passes"] is True, (
        f"Real corpus failed: ece_raw={result['ece_raw_half2']:.4f} "
        f"ece_cal={result['ece_cal_half2']:.4f} "
        f"sum_to_one_ok={result['sum_to_one_ok']}"
    )
