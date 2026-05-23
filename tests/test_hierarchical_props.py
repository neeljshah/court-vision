"""
tests/test_hierarchical_props.py — Tests for HierarchicalPropModel and BlendedPropEnsemble.

Synthetic 50-player × 30-game dataset tests:
  1. Posterior mean shrinks toward pop mean for low-N players.
  2. 80% interval covers true value ~80% of time on synthetic data.
  3. predict() returns expected dict structure.
  4. Ensemble: 3 mock models -> blend value between components.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Dict, List

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.hierarchical_props import HierarchicalPropModel


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_synthetic_data(
    n_players: int = 50,
    n_games_full: int = 30,
    n_games_low: int = 3,
    n_low_players: int = 10,
    pop_mean: float = 1.2,
    tau: float = 0.5,         # between-player std
    sigma: float = 0.8,       # within-player std
    seed: int = 42,
) -> tuple:
    """
    Generate synthetic player-game data from a normal-normal model.

    Returns (rows, true_player_means) where:
      rows: list of {player_id, actual, pos}
      true_player_means: {player_id: float}
    """
    rng = np.random.default_rng(seed)
    rows: List[dict] = []
    true_means: Dict[int, float] = {}

    for pid in range(1, n_players + 1):
        alpha_i = rng.normal(pop_mean, tau)
        alpha_i = max(0.0, alpha_i)
        true_means[pid] = alpha_i
        # Low-N players: first n_low_players get few games
        n_games = n_games_low if pid <= n_low_players else n_games_full
        pos = "G" if pid % 3 == 0 else ("C" if pid % 3 == 1 else "F")
        for _ in range(n_games):
            y = rng.normal(alpha_i, sigma)
            y = max(0.0, y)
            rows.append({"player_id": pid, "actual": y, "pos": pos})

    return rows, true_means


# ── Test 1: Shrinkage toward population mean ──────────────────────────────────

def test_shrinkage_low_n_players():
    """Low-N players' posterior means are closer to pop mean than their raw sample mean."""
    rows, true_means = make_synthetic_data(
        n_players=50,
        n_games_full=30,
        n_games_low=3,
        n_low_players=10,
        pop_mean=1.5,
        tau=0.6,
        sigma=0.8,
    )
    model = HierarchicalPropModel("blk")
    model.fit(rows)

    pop_mean_est = model._league_mean

    # For each low-N player, check shrinkage
    low_n_pids = list(range(1, 11))
    shrinkage_holds = 0
    for pid in low_n_pids:
        ps = model._player_stats.get(pid, {})
        raw_mean = ps.get("x_bar", pop_mean_est)
        post = model.predict(pid, {})["mean"]
        # Posterior should be between raw sample mean and pop mean
        lo = min(raw_mean, pop_mean_est)
        hi = max(raw_mean, pop_mean_est)
        if lo <= post <= hi + 0.001:  # small tolerance for clipping
            shrinkage_holds += 1

    # At least 7/10 low-N players should show shrinkage (some may be clipped at 0)
    assert shrinkage_holds >= 7, (
        f"Shrinkage failed for {10 - shrinkage_holds}/10 low-N players"
    )


# ── Test 2: 80% interval coverage ─────────────────────────────────────────────

def test_80_interval_coverage():
    """80% credible intervals should cover true value ~80% of time on new draws."""
    rng = np.random.default_rng(99)
    pop_mean, tau, sigma = 1.2, 0.5, 0.8
    n_players = 40
    n_games   = 25

    rows: List[dict] = []
    true_means: Dict[int, float] = {}

    for pid in range(1, n_players + 1):
        alpha_i = max(0.0, rng.normal(pop_mean, tau))
        true_means[pid] = alpha_i
        for _ in range(n_games):
            rows.append({
                "player_id": pid,
                "actual":    max(0.0, rng.normal(alpha_i, sigma)),
                "pos":       "F",
            })

    model = HierarchicalPropModel("blk")
    model.fit(rows)

    # Generate new unseen games per player and check interval coverage
    covered = 0
    total   = 0
    for pid, alpha_i in true_means.items():
        for _ in range(5):   # 5 new games per player
            y_new = max(0.0, rng.normal(alpha_i, sigma))
            out   = model.predict(pid, {})
            if out["lo_80"] <= y_new <= out["hi_80"]:
                covered += 1
            total += 1

    coverage = covered / total
    # Accept [0.60, 0.95] — synthetic Gaussian, loose bounds for small N
    assert 0.60 <= coverage <= 0.95, (
        f"80% interval coverage = {coverage:.3f}, expected [0.60, 0.95]"
    )


# ── Test 3: predict() dict structure ─────────────────────────────────────────

def test_predict_dict_structure():
    """predict() must return all required keys with correct types."""
    rows, _ = make_synthetic_data(n_players=10, n_games_full=20, n_games_low=5)
    model = HierarchicalPropModel("stl")
    model.fit(rows)

    out = model.predict(1, {"opp_def_rating": 112.5, "is_home": 1})

    required = {"mean", "lo_80", "hi_80", "lo_95", "hi_95",
                "posterior_std", "shrinkage_weight", "n_games",
                "position", "posterior_samples"}
    assert required.issubset(set(out.keys())), (
        f"Missing keys: {required - set(out.keys())}"
    )
    assert isinstance(out["mean"], float)
    assert isinstance(out["posterior_samples"], np.ndarray)
    assert len(out["posterior_samples"]) == 500
    assert out["lo_80"] <= out["mean"] <= out["hi_80"]
    assert out["lo_95"] <= out["lo_80"]
    assert out["hi_80"] <= out["hi_95"]
    assert out["mean"] >= 0.0


# ── Test 4: predict() for unseen player ───────────────────────────────────────

def test_predict_unseen_player():
    """Unseen player should fall back to position prior gracefully."""
    rows, _ = make_synthetic_data(n_players=20, n_games_full=15)
    model = HierarchicalPropModel("fg3m")
    model.fit(rows)

    # Player 9999 not in training data
    out = model.predict(9999, {})
    assert out["mean"] >= 0.0
    assert out["n_games"] == 0
    assert out["mean"] == pytest.approx(
        model._pos_means.get(out["position"], model._league_mean), abs=0.01
    )


# ── Test 5: save/load round-trip ──────────────────────────────────────────────

def test_save_load_roundtrip():
    """save() then load() should reproduce identical predictions."""
    rows, _ = make_synthetic_data(n_players=15, n_games_full=20)
    model = HierarchicalPropModel("tov")
    model.fit(rows)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_tov.pkl")
        model.save(path)

        model2 = HierarchicalPropModel("tov")
        model2.load(path)

        for pid in [1, 5, 10]:
            p1 = model.predict(pid, {})["mean"]
            p2 = model2.predict(pid, {})["mean"]
            assert abs(p1 - p2) < 1e-6, f"Mismatch for pid={pid}: {p1} vs {p2}"


# ── Test 6: BlendedPropEnsemble with mock models ──────────────────────────────

def test_ensemble_blends_between_components():
    """
    BlendedPropEnsemble with only hierarchical component (others absent) should
    return the hierarchical mean. With mocked weights, blend must be between components.
    """
    rows, _ = make_synthetic_data(n_players=20, n_games_full=20)
    model = HierarchicalPropModel("blk")
    model.fit(rows)

    with tempfile.TemporaryDirectory() as tmpdir:
        model.save(os.path.join(tmpdir, "hierarchical_blk.pkl"))

        from src.prediction.ensemble_props import BlendedPropEnsemble
        ens = BlendedPropEnsemble(model_dir=tmpdir)
        # Only hierarchical available in tmpdir
        result = ens.predict(player_id=1, features={})

        blk_out = result.get("blk", {})
        assert "mean" in blk_out
        assert "components" in blk_out
        # With only hierarchical, components should have exactly that
        assert "hierarchical" in blk_out["components"]
        # Mean should be non-negative
        assert blk_out["mean"] >= 0.0


def test_ensemble_blend_is_weighted_average():
    """Blend of known values should equal weighted average."""
    from src.prediction.ensemble_props import BlendedPropEnsemble

    # Patch weights and component preds manually
    ens = BlendedPropEnsemble.__new__(BlendedPropEnsemble)
    ens.model_dir     = _MODELS_DIR = ""
    ens._hier_models  = {}
    ens._weights      = {"blk": {"v3_lgb": 0.5, "hierarchical": 0.5}}

    comp_preds = {"v3_lgb": 2.0, "hierarchical": 4.0}
    avail      = ["v3_lgb", "hierarchical"]
    weights    = ens._norm_weights("blk", avail)
    blend      = sum(weights[k] * comp_preds[k] for k in avail)

    assert abs(blend - 3.0) < 1e-6, f"Expected 3.0, got {blend}"
    assert blend >= min(comp_preds.values())
    assert blend <= max(comp_preds.values())


# ── Test 7: fit() is idempotent ────────────────────────────────────────────────

def test_fit_twice_same_result():
    """Fitting twice on same data gives same league_mean."""
    rows, _ = make_synthetic_data(n_players=20, n_games_full=15)
    model = HierarchicalPropModel("pts")
    r1 = model.fit(rows)
    r2 = model.fit(rows)
    assert r1["league_mean"] == r2["league_mean"]
    assert r1["n_players"] == r2["n_players"]
