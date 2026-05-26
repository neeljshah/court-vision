"""tests/test_R31_X3_multitask_mlp.py

Validates the R31_X3 multitask MLP probe artifacts + helpers:
  1. Probe module imports cleanly
  2. Model factory builds a torch module with correct shapes
  3. Seed-ensemble training is reproducible (same seed -> same predictions)
  4. Seed-ensemble averaging is the simple mean (no NaN, correct shape)
  5. Persisted artifacts (when present) load + predict without NaN
"""
from __future__ import annotations

import importlib
import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

torch = pytest.importorskip("torch")

probe = importlib.import_module(
    "scripts.improve_loop.probe_R31_X3_m2_multitask_mlp"
)


def _toy_train_data(n: int = 200, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, 74)).astype(np.float32)
    # 4 weakly-correlated targets in different scales (matches m2 targets)
    base = X[:, :4] @ rng.standard_normal((4, 1))
    Y = np.column_stack([
        220.0 + 5.0 * base.squeeze() + rng.standard_normal(n) * 5.0,  # total
        0.0 + 3.0 * base.squeeze() + rng.standard_normal(n) * 5.0,    # spread
        110.0 + 4.0 * base.squeeze() + rng.standard_normal(n) * 3.0,  # home_pts
        110.0 + rng.standard_normal(n) * 3.0,                          # away_pts
    ]).astype(np.float32)
    return X, Y


def test_probe_imports():
    assert hasattr(probe, "TARGETS")
    assert set(probe.TARGETS.keys()) == {"total", "spread", "home_pts", "away_pts"}
    assert probe.TARGET_ORDER == ["total", "spread", "home_pts", "away_pts"]
    assert probe.MLP_SEEDS == [42, 7, 100]
    assert len(probe.FEAT_COLS) == 74


def test_model_factory_shapes():
    model = probe._build_torch_model(n_features=74, n_targets=4, dropout=0.2)
    model.eval()
    x = torch.zeros(8, 74)
    with torch.no_grad():
        y = model(x)
    assert y.shape == (8, 4), f"expected (8,4), got {tuple(y.shape)}"
    # No NaNs from a zero input
    assert not torch.isnan(y).any().item()


def test_seed_reproducibility():
    """Same seed + same data -> same weights -> same predictions."""
    X, Y = _toy_train_data()
    m1, mu1, sd1 = probe.train_multitask_mlp(X, Y, seed=42, max_epochs=5)
    m2, mu2, sd2 = probe.train_multitask_mlp(X, Y, seed=42, max_epochs=5)
    np.testing.assert_array_equal(mu1, mu2)
    np.testing.assert_array_equal(sd1, sd2)
    p1 = probe.predict_multitask_mlp(m1, X[:16], mu1, sd1)
    p2 = probe.predict_multitask_mlp(m2, X[:16], mu2, sd2)
    np.testing.assert_allclose(p1, p2, atol=1e-5)


def test_seed_ensemble_is_mean_no_nan():
    X, Y = _toy_train_data()
    ens = probe.train_mlp_seed_ensemble(X, Y, seeds=[42, 7, 100])
    assert len(ens) == 3
    seeds_seen = [s for s, _, _, _ in ens]
    assert seeds_seen == [42, 7, 100]

    # Ensemble = mean of per-seed predictions
    Xq = X[:32]
    per_seed = np.stack([
        probe.predict_multitask_mlp(m, Xq, mu, sd) for _, m, mu, sd in ens
    ])  # (3, 32, 4)
    expected = per_seed.mean(axis=0)
    got = probe.predict_mlp_ensemble(ens, Xq)
    np.testing.assert_allclose(got, expected, atol=1e-6)
    assert got.shape == (32, 4)
    assert not np.isnan(got).any()


def test_per_target_shape_and_finite():
    X, Y = _toy_train_data()
    ens = probe.train_mlp_seed_ensemble(X, Y, seeds=[42, 7, 100])
    preds = probe.predict_mlp_ensemble(ens, X)
    assert preds.shape == (len(X), 4)
    assert np.isfinite(preds).all()
    # Sanity-check: predictions should be roughly in target ranges
    means = preds.mean(axis=0)
    assert 150 < means[0] < 300, f"total mean={means[0]:.1f} out of plausible range"
    assert 80 < means[2] < 150, f"home_pts mean={means[2]:.1f} out of plausible range"


def test_persisted_artifacts_loadable():
    """If R31_X3 SHIP persisted artifacts, ensure they load + predict cleanly."""
    art_dir = probe.ROOT_MODELS_DIR_NEW
    if not os.path.isdir(art_dir):
        pytest.skip("R31_X3 artifacts not persisted yet")
    manifest_p = os.path.join(art_dir, "manifest.json")
    if not os.path.exists(manifest_p):
        pytest.skip("manifest.json missing")
    import json
    with open(manifest_p) as f:
        man = json.load(f)
    seed_models = man.get("seed_models", [])
    assert seed_models, "manifest has no seed_models"
    n_features = int(man.get("n_features", 74))

    rng = np.random.default_rng(0)
    Xq = rng.standard_normal((4, n_features)).astype(np.float32)

    preds_acc = []
    for lab in seed_models:
        ckpt_p = os.path.join(art_dir, f"{lab}.pt")
        assert os.path.exists(ckpt_p), f"missing checkpoint {ckpt_p}"
        ckpt = torch.load(ckpt_p, map_location="cpu", weights_only=False)
        model = probe._build_torch_model(
            n_features=ckpt["n_features"],
            n_targets=ckpt["n_targets"],
            dropout=0.2,
        )
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        mu = np.asarray(ckpt["mu_y"])
        sd = np.asarray(ckpt["sd_y"])
        with torch.no_grad():
            p = model(torch.from_numpy(Xq)).cpu().numpy() * sd + mu
        assert p.shape == (4, 4)
        assert np.isfinite(p).all()
        preds_acc.append(p)
    ensemble_pred = np.mean(np.stack(preds_acc), axis=0)
    assert ensemble_pred.shape == (4, 4)
    assert np.isfinite(ensemble_pred).all()
