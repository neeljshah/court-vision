"""test_play_probability.py — cycle 104a (loop 5) unit tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import play_probability as pp  # noqa: E402


def _synthetic(n=2000, seed=0):
    """b2b veterans (is_b2b=1, age>=33) play with prob 0.2;
    everyone else plays with prob 0.9."""
    rng = np.random.default_rng(seed)
    n_feats = len(pp.PLAY_PROB_FEATURES)
    X = np.zeros((n, n_feats), dtype=float)
    idx_b2b = pp.PLAY_PROB_FEATURES.index("is_b2b")
    idx_age = pp.PLAY_PROB_FEATURES.index("age")
    idx_days = pp.PLAY_PROB_FEATURES.index("days_since_last_game")
    idx_pace = pp.PLAY_PROB_FEATURES.index("opp_team_pace_l5")
    y = np.zeros(n, dtype=int)
    for i in range(n):
        is_vet_b2b = rng.random() < 0.25
        if is_vet_b2b:
            X[i, idx_b2b] = 1.0
            X[i, idx_age] = rng.uniform(33, 38)
            X[i, idx_days] = 1.0
            p = 0.2
        else:
            X[i, idx_b2b] = 0.0
            X[i, idx_age] = rng.uniform(22, 30)
            X[i, idx_days] = rng.uniform(2, 4)
            p = 0.9
        X[i, idx_pace] = 100.0
        y[i] = 1 if rng.random() < p else 0
    return X, y


def test_train_learns_b2b_signal():
    X, y = _synthetic(n=2000, seed=1)
    art = pp.train_play_probability(X, y, val_frac=0.2)
    # Build a vet-b2b feature row and a non-vet feature row.
    vet = {c: 0.0 for c in pp.PLAY_PROB_FEATURES}
    vet["is_b2b"] = 1.0
    vet["age"] = 35.0
    vet["days_since_last_game"] = 1.0
    vet["opp_team_pace_l5"] = 100.0
    young = {c: 0.0 for c in pp.PLAY_PROB_FEATURES}
    young["is_b2b"] = 0.0
    young["age"] = 25.0
    young["days_since_last_game"] = 3.0
    young["opp_team_pace_l5"] = 100.0
    p_vet = pp.predict_play_probability(vet, artifact=art)
    p_young = pp.predict_play_probability(young, artifact=art)
    assert p_vet is not None and p_young is not None
    assert p_vet < p_young, f"vet b2b ({p_vet:.3f}) should be < young ({p_young:.3f})"


def test_calibration_close_to_played_fraction():
    X, y = _synthetic(n=2000, seed=2)
    art = pp.train_play_probability(X, y, val_frac=0.2)
    # Mean calibrated P(play) on val should be close to actual played frac.
    gap = abs(art["val_mean_pred"] - art["val_played_frac"])
    assert gap < 0.08, f"calibration gap {gap:.3f} > 0.08"


def test_probability_clipped_to_range():
    X, y = _synthetic(n=2000, seed=3)
    art = pp.train_play_probability(X, y, val_frac=0.2)
    # Even with extreme features, must stay in [0.01, 1.0].
    extreme = {c: 1e9 for c in pp.PLAY_PROB_FEATURES}
    p = pp.predict_play_probability(extreme, artifact=art)
    assert p is not None
    assert pp._PLAY_PROB_MIN <= p <= pp._PLAY_PROB_MAX


def test_blend_at_p1_is_identity(monkeypatch):
    monkeypatch.setattr(pp, "_APPLY_PLAY_PROB", True)
    # Fake artifact whose calibrator + model both produce ~1.0.
    class _Stub:
        def predict_proba(self, X):
            return np.array([[0.0, 1.0]])
    art = {"model": _Stub(), "platt_a": 1000.0, "platt_b": 1000.0,
           "features": list(pp.PLAY_PROB_FEATURES)}
    fr = {c: 0.0 for c in pp.PLAY_PROB_FEATURES}
    out = pp.apply_play_prob_blend(10.0, fr, artifact=art)
    assert abs(out - 10.0) < 1e-6


def test_blend_at_p0_zeroes_pred(monkeypatch):
    monkeypatch.setattr(pp, "_APPLY_PLAY_PROB", True)
    # We can't hit exactly 0 because of clip; should produce 10 * 0.01 = 0.1.
    class _Stub:
        def predict_proba(self, X):
            return np.array([[1.0, 0.0]])
    art = {"model": _Stub(), "platt_a": 1000.0, "platt_b": -1000.0,
           "features": list(pp.PLAY_PROB_FEATURES)}
    fr = {c: 0.0 for c in pp.PLAY_PROB_FEATURES}
    out = pp.apply_play_prob_blend(10.0, fr, artifact=art)
    assert out == pytest.approx(10.0 * pp._PLAY_PROB_MIN, abs=1e-6)


def test_missing_artifact_is_noop(tmp_path, monkeypatch):
    # Default flag is False -> always no-op regardless of artifact.
    fr = {c: 0.0 for c in pp.PLAY_PROB_FEATURES}
    out = pp.apply_play_prob_blend(7.5, fr, model_dir=str(tmp_path))
    assert out == 7.5
    # Even with flag ON, missing artifact => no-op.
    monkeypatch.setattr(pp, "_APPLY_PLAY_PROB", True)
    out2 = pp.apply_play_prob_blend(7.5, fr, model_dir=str(tmp_path))
    assert out2 == 7.5


def test_dnp_parquet_covers_2025_26_holdout():
    """cycle 105a: DNP parquet must include the 2025-26 holdout window
    so the P(play) head trains on the same date range used for evaluation.

    Pre-cycle-105a the parquet ended 2025-04-13 (cycle 104a REJECT root
    cause). After re-aggregating against the 2025-26 boxscore backfill the
    holdout window 2025-10-31..2026-04-12 must have non-trivial DNP rows.
    """
    import pandas as pd
    parq = os.path.join(PROJECT_DIR, "data", "dnp_rows.parquet")
    if not os.path.exists(parq):
        pytest.skip("dnp_rows.parquet not present in this checkout")
    df = pd.read_parquet(parq)
    h = df[(df["game_date"] >= "2025-10-31") & (df["game_date"] <= "2026-04-12")]
    assert len(h) > 100, (
        f"2025-26 holdout DNP coverage too thin: {len(h)} rows. "
        "Re-run scripts/aggregate_dnp_rows.py against the boxscore cache."
    )
