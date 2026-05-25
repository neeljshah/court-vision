"""Tests for src.prediction.multitask_mlp_live (tier3-9, loop 5)."""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

torch = pytest.importorskip("torch", reason="torch needed for multitask_mlp_live")

from src.prediction.multitask_mlp_live import (  # noqa: E402
    LIVE_DIM,
    LIVE_FEATURE_NAMES,
    MultitaskMLPLive,
    STATS,
    build_live_vector,
    build_target_matrix,
)


PRE_DIM = 32  # toy pregame dim for synthetic tests


def _make_synthetic(n: int = 1000, pre_dim: int = PRE_DIM, seed: int = 0):
    """Build a synthetic two-input dataset with learnable structure."""
    rng = np.random.default_rng(seed)
    X_pre = rng.standard_normal((n, pre_dim)).astype(np.float32)
    X_live = rng.standard_normal((n, LIVE_DIM)).astype(np.float32)
    # Each stat is a different linear combination of pregame + live so the
    # multitask head must learn 7 different weightings.
    W_pre = rng.standard_normal((pre_dim, len(STATS))).astype(np.float32) * 0.3
    W_live = rng.standard_normal((LIVE_DIM, len(STATS))).astype(np.float32) * 0.1
    bias = np.array([12.0, 5.0, 3.0, 1.0, 0.8, 0.5, 1.2], dtype=np.float32)
    noise = rng.standard_normal((n, len(STATS))).astype(np.float32) * 0.5
    Y_raw = X_pre @ W_pre + X_live @ W_live + bias + noise
    Y_raw = np.clip(Y_raw, 0.0, None)
    # Apply transforms (same as production).
    rows = [{f"target_{s}": float(Y_raw[i, j])
             for j, s in enumerate(STATS)} for i in range(n)]
    Y = build_target_matrix(rows)
    return X_pre, X_live, Y, Y_raw


def test_forward_pass_produces_7_dim_output():
    model = MultitaskMLPLive(pregame_dim=PRE_DIM)
    model._build_module()
    # Manually set scalers so predict doesn't error on un-fit state.
    model.scaler_mean = np.zeros(PRE_DIM, dtype=np.float32)
    model.scaler_std = np.ones(PRE_DIM, dtype=np.float32)
    model.live_mean = np.zeros(LIVE_DIM, dtype=np.float32)
    model.live_std = np.ones(LIVE_DIM, dtype=np.float32)
    X_pre = np.ones((3, PRE_DIM), dtype=np.float32)
    out = model.predict(X_pre, invert=False)
    assert out.shape == (3, len(STATS)), \
        f"expected (3, {len(STATS)}), got {out.shape}"


def test_zero_live_input_matches_explicit_zero_within_tolerance():
    """Zero-live-input back-compat: pred(X_pre, None) must equal pred(X_pre, zeros)."""
    X_pre, X_live, Y, _ = _make_synthetic(n=400, seed=1)
    model = MultitaskMLPLive(pregame_dim=PRE_DIM, seed=1)
    model.fit(X_pre[:300], X_live[:300] * 0.0, Y[:300],
              X_pre_val=X_pre[300:], X_live_val=X_live[300:] * 0.0,
              Y_val=Y[300:], epochs=8, batch_size=64)
    # Compare implicit None vs explicit zero vector.
    X_test = X_pre[300:320]
    pred_none = model.predict(X_test, None, invert=True)
    pred_zero = model.predict(X_test, np.zeros((20, LIVE_DIM), dtype=np.float32),
                              invert=True)
    delta = float(np.mean(np.abs(pred_none - pred_zero)))
    # The two paths must be functionally identical (no model stochasticity
    # at inference); 0.005 is the spec'd back-compat tolerance.
    assert delta < 0.005, f"zero-input back-compat delta {delta:.6f} exceeds 0.005"


def test_live_input_nonzero_changes_output():
    """When live input is non-zero, the prediction must differ from zero-input."""
    X_pre, X_live, Y, _ = _make_synthetic(n=400, seed=2)
    model = MultitaskMLPLive(pregame_dim=PRE_DIM, seed=2)
    model.fit(X_pre[:300], X_live[:300], Y[:300],
              X_pre_val=X_pre[300:], X_live_val=X_live[300:], Y_val=Y[300:],
              epochs=12, batch_size=64)
    X_test = X_pre[300:320]
    L_test = X_live[300:320]
    pred_live = model.predict(X_test, L_test, invert=True)
    pred_zero = model.predict(X_test, None, invert=True)
    delta = float(np.mean(np.abs(pred_live - pred_zero)))
    assert delta > 0.005, \
        f"live input had no effect on output (mean abs diff {delta:.6f})"


def test_training_on_synthetic_converges():
    """Loss must decrease meaningfully over training."""
    X_pre, X_live, Y, _ = _make_synthetic(n=1000, seed=3)
    model = MultitaskMLPLive(pregame_dim=PRE_DIM, seed=3)
    model.fit(X_pre[:800], X_live[:800], Y[:800],
              X_pre_val=X_pre[800:], X_live_val=X_live[800:], Y_val=Y[800:],
              epochs=20, batch_size=128, patience=20)
    history = model.train_history.get("history") or []
    assert len(history) >= 2, "no training history recorded"
    losses = [h["train_loss"] for h in history if "train_loss" in h]
    assert len(losses) >= 2
    # Last epoch loss must be at least 25% below the first.
    assert losses[-1] < 0.75 * losses[0], (
        f"loss did not converge: first={losses[0]:.4f} last={losses[-1]:.4f}")


def test_save_load_roundtrip_preserves_predictions():
    """Persisted artifact reloads with identical predictions."""
    X_pre, X_live, Y, _ = _make_synthetic(n=400, seed=4)
    model = MultitaskMLPLive(pregame_dim=PRE_DIM, seed=4)
    model.feature_names = [f"f{i}" for i in range(PRE_DIM)]
    model.fit(X_pre[:300], X_live[:300], Y[:300],
              X_pre_val=X_pre[300:], X_live_val=X_live[300:], Y_val=Y[300:],
              epochs=8, batch_size=64)
    X_test, L_test = X_pre[300:310], X_live[300:310]
    pred_before = model.predict(X_test, L_test, invert=True)

    with tempfile.TemporaryDirectory() as td:
        mpath = os.path.join(td, "m.pt")
        meta = os.path.join(td, "m.json")
        model.save(model_path=mpath, meta_path=meta)
        loaded = MultitaskMLPLive.load(model_path=mpath, meta_path=meta)
    assert loaded is not None
    pred_after = loaded.predict(X_test, L_test, invert=True)
    delta = float(np.mean(np.abs(pred_before - pred_after)))
    assert delta < 1e-5, f"roundtrip prediction drift {delta:.8f}"
    assert loaded.feature_names == model.feature_names
    assert loaded.pregame_dim == model.pregame_dim


def test_inference_handles_missing_live_features_via_zero_pad():
    """build_live_vector with None / partial snapshot must produce safe vector."""
    # None snapshot -> all-zero vector.
    v0 = build_live_vector(None)
    assert v0.shape == (LIVE_DIM,)
    assert np.all(v0 == 0.0)
    # Empty dict -> all-zero vector.
    v1 = build_live_vector({})
    assert np.all(v1 == 0.0)
    # Partial snapshot -> only specified keys are non-zero.
    snap = {"period": 4, "current_pts": 22.0, "current_pf": 3,
            "irrelevant_key": 999.0}
    v2 = build_live_vector(snap)
    idx_period = LIVE_FEATURE_NAMES.index("period")
    idx_pts = LIVE_FEATURE_NAMES.index("current_pts")
    idx_pf = LIVE_FEATURE_NAMES.index("current_pf")
    assert v2[idx_period] == 4.0
    assert v2[idx_pts] == 22.0
    assert v2[idx_pf] == 3.0
    # The rest must be zero.
    nonzero_idx = {idx_period, idx_pts, idx_pf}
    for i in range(LIVE_DIM):
        if i not in nonzero_idx:
            assert v2[i] == 0.0, f"slot {i} ({LIVE_FEATURE_NAMES[i]}) leaked"
    # NaN / non-numeric values are scrubbed to zero (back-compat with the
    # 'safe for live dashboards' contract).
    v3 = build_live_vector({"current_pts": float("nan"),
                             "current_min": "not-a-number"})
    assert np.all(v3 == 0.0)

    # And the model must accept these as inference input.
    model = MultitaskMLPLive(pregame_dim=PRE_DIM)
    model._build_module()
    model.scaler_mean = np.zeros(PRE_DIM, dtype=np.float32)
    model.scaler_std = np.ones(PRE_DIM, dtype=np.float32)
    model.live_mean = np.zeros(LIVE_DIM, dtype=np.float32)
    model.live_std = np.ones(LIVE_DIM, dtype=np.float32)
    X_pre = np.zeros((1, PRE_DIM), dtype=np.float32)
    pred = model.predict_one(X_pre[0], snapshot=None)
    assert set(pred.keys()) == set(STATS)
    for s in STATS:
        assert isinstance(pred[s], float)
