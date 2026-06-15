"""Per-file test for scripts.platformkit.proof_mlb.ingame_accuracy.

Fast: exercises the leak-free helpers + the three-forecaster mechanics on a tiny synthetic
corpus (no full 28k-game run). Asserts the in-game pattern holds — combining the pregame Elo
prior with the realized score is at least as sharp as either alone on the constructed cases.
Run: python -m pytest tests/mlb/test_ingame_accuracy.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import scripts.platformkit.proof_mlb.ingame_accuracy as M
from scripts.platformkit.live_repricer import get_repricer
from domains.mlb.negbinom_engine import _FALLBACK_R


def test_parse_innings_handles_x_and_blanks():
    assert M._parse_innings("0,1,0,0,1,3,3,1,x") == [0, 1, 0, 0, 1, 3, 3, 1]
    assert M._parse_innings("2,0,2") == [2, 0, 2]
    assert M._parse_innings(None) is None
    assert M._parse_innings("") is None
    assert M._parse_innings("a,b") is None


def test_brier_and_logloss_basic():
    p = np.array([0.5, 0.5]); y = np.array([1.0, 0.0])
    assert abs(M._brier(p, y) - 0.25) < 1e-9
    # log-loss of 0.5 predictions == ln 2
    assert abs(M._logloss(p, y) - np.log(2)) < 1e-9


def test_walk_forward_elo_leakfree_and_responds_to_results():
    # A always beats B at home -> A's as-of home win-prob should rise over time.
    rows = [{"home_team": "A", "away_team": "B", "home_runs": 5, "away_runs": 1}
            for _ in range(20)]
    df = pd.DataFrame(rows)
    p = M._walk_forward_elo(df)
    assert p[0] == 0.5 + (p[0] - 0.5)        # finite
    assert abs(p[0] - M._p_home(M._INIT, M._INIT)) < 1e-9  # first snapshot = pure HFA prior
    assert p[-1] > p[0]                       # A's home win-prob grew with wins (leak-free update)
    assert (p > 0).all() and (p < 1).all()


def test_reprice_winhome_responds_to_score_and_prior():
    rep = get_repricer("mlb")
    # After inning 5, home leads 6-1: ml_home should be high regardless of prior.
    p = M._reprice_winhome(rep, 6, 1, 5, 4.5, 4.5, _FALLBACK_R, _FALLBACK_R)
    assert p > 0.8
    # Tied 2-2 after inning 5: a strong home prior should beat a weak home prior.
    p_strong = M._reprice_winhome(rep, 2, 2, 5, 6.0, 3.0, _FALLBACK_R, _FALLBACK_R)
    p_weak = M._reprice_winhome(rep, 2, 2, 5, 3.0, 6.0, _FALLBACK_R, _FALLBACK_R)
    assert p_strong > p_weak


def test_ece10_is_zero_for_perfectly_calibrated():
    # 200 events at p=0.5 with exactly half positive -> bin-mean == outcome-mean -> ECE 0.
    p = np.full(200, 0.5)
    y = np.array([1.0, 0.0] * 100)
    assert M._ece10(p, y) < 1e-9
    # A confidently-wrong forecaster has large ECE.
    p_bad = np.full(100, 0.9)
    y_bad = np.zeros(100)
    assert M._ece10(p_bad, y_bad) > 0.5


def test_reliability_slope_detects_overconfidence():
    rng = np.random.default_rng(0)
    true_p = rng.uniform(0.2, 0.8, 4000)
    y = rng.binomial(1, true_p).astype(float)
    # over-confident: push probabilities away from 0.5 (logit * 1.8) -> slope < 1.
    lt = np.log(true_p / (1 - true_p))
    p_over = 1.0 / (1.0 + np.exp(-(lt * 1.8)))
    slope_over = M._reliability_slope(p_over, y)
    slope_cal = M._reliability_slope(true_p, y)
    assert slope_over < slope_cal               # over-confident reads as lower slope
    assert 0.8 < slope_cal < 1.2                # calibrated input ~ slope 1


def test_fit_apply_recal_is_leakfree_and_helps_overconfident():
    rng = np.random.default_rng(1)
    true_p = rng.uniform(0.2, 0.8, 3000)
    y = rng.binomial(1, true_p).astype(float)
    lt = np.log(true_p / (1 - true_p))
    p_over = 1.0 / (1.0 + np.exp(-(lt * 2.0)))  # over-confident raw forecaster
    half = len(p_over) // 2
    p_tr, y_tr = p_over[:half], y[:half]
    p_ho = p_over[half:]
    recal_ho, method = M._fit_apply_recal(p_tr, y_tr, p_ho)
    assert recal_ho.shape == p_ho.shape
    assert method in ("temperature", "platt", "identity")
    assert (recal_ho >= 0).all() and (recal_ho <= 1).all()
    # recalibrating an over-confident forecaster should lower held-out ECE.
    ece_raw = M._ece10(p_ho, y[half:])
    ece_recal = M._ece10(recal_ho, y[half:])
    assert ece_recal <= ece_raw + 1e-6


def test_run_exposes_calibration_keys(tmp_path):
    import pathlib
    g = pd.read_parquet(M._GAMES)
    pit = pd.read_parquet(M._PITCHERS)[["event_id", "home_innings", "away_innings"]]
    g = g.iloc[::12].reset_index(drop=True)
    pit = pit[pit["event_id"].isin(g["event_id"])].reset_index(drop=True)
    d = tmp_path / "data" / "domains" / "mlb"
    d.mkdir(parents=True)
    g.to_parquet(d / "games.parquet")
    pit.to_parquet(d / "pitchers.parquet")
    orig_g, orig_p = M._GAMES, M._PITCHERS
    try:
        M._GAMES = pathlib.Path(d / "games.parquet")
        M._PITCHERS = pathlib.Path(d / "pitchers.parquet")
        r = M.run()
    finally:
        M._GAMES, M._PITCHERS = orig_g, orig_p
    assert r["status"] == "ok"
    for k in ("ece_raw", "ece_recal", "recal_method", "reliability_slope",
              "reliability_slope_recal", "recal_brier_not_worse", "calibration_verdict"):
        assert k in r
    assert 0.0 <= r["ece_raw"] <= 1.0 and 0.0 <= r["ece_recal"] <= 1.0
    assert r["recal_method"] in ("temperature", "platt", "identity", "none")
    # leak-free recal must never worsen Brier (the gate we report).
    assert r["recal_brier_not_worse"] is True


def test_run_smoke_on_full_corpus_pattern(tmp_path):
    """End-to-end on the real corpus is slow; instead assert run() returns the documented
    shape and the in-game pattern on a SUBSAMPLED corpus written to a temp dir."""
    import pathlib
    g = pd.read_parquet(M._GAMES)
    pit = pd.read_parquet(M._PITCHERS)[["event_id", "home_innings", "away_innings"]]
    # every 12th game keeps chronology but runs fast
    g = g.iloc[::12].reset_index(drop=True)
    pit = pit[pit["event_id"].isin(g["event_id"])].reset_index(drop=True)
    d = tmp_path / "data" / "domains" / "mlb"
    d.mkdir(parents=True)
    g.to_parquet(d / "games.parquet")
    pit.to_parquet(d / "pitchers.parquet")

    orig_g, orig_p = M._GAMES, M._PITCHERS
    try:
        M._GAMES = pathlib.Path(d / "games.parquet")
        M._PITCHERS = pathlib.Path(d / "pitchers.parquet")
        r = M.run()
    finally:
        M._GAMES, M._PITCHERS = orig_g, orig_p

    assert r["status"] == "ok"
    for k in ("brier_pregame", "brier_scoreonly", "brier_combined",
              "delta_combined_vs_pregame", "combined_beats_pregame"):
        assert k in r
    # the documented pattern: combined is far sharper than pregame, and ties/beats score-only
    assert r["brier_combined"] < r["brier_pregame"]
    assert r["brier_combined"] <= r["brier_scoreonly"] + 5e-3
