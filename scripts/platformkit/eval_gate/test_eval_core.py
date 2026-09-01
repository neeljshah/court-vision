"""Per-file tests for the eval-gate pure core (blueprint N1).

Runs under pytest. numpy + stdlib only.
Proves the math + the leak guard + the cluster-robust DM behavior the gate relies on.
"""
from __future__ import annotations
from math import atan, pi
import numpy as np
import pytest

from scripts.platformkit.eval_gate.scoring import (
    brier, log_loss, brier_skill_score, ece, resolution, sharpness,
    crps_gaussian, crps_ensemble, pinball_loss,
)
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.schema import validate_golden


def test_brier_known_values():
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert abs(brier([0.5, 0.5], [1, 0]) - 0.25) < 1e-12


def test_log_loss_monotone():
    # confident-correct beats hedged beats confident-wrong
    confident_right = log_loss([0.99, 0.01], [1, 0])
    hedged = log_loss([0.5, 0.5], [1, 0])
    confident_wrong = log_loss([0.01, 0.99], [1, 0])
    assert confident_right < hedged < confident_wrong


def test_bss_sign():
    y = [1, 0, 1, 0, 1, 0]
    sharp = [0.9, 0.1, 0.8, 0.2, 0.95, 0.05]   # tracks outcomes
    flat = [0.5] * 6                            # the close-ish baseline
    assert brier_skill_score(sharp, flat, y) > 0          # sharp beats flat
    assert brier_skill_score(flat, sharp, y) < 0          # flat behind sharp (honest)


def test_ece_collapse_guard():
    # predicting the base rate everywhere -> low ECE but ~zero sharpness/resolution
    y = np.array([1, 0] * 50)
    flat = np.full(100, 0.5)
    assert ece(flat, y) < 0.05            # looks "calibrated"
    assert sharpness(flat) < 1e-9         # but is not sharp at all
    assert resolution(flat, y) < 1e-9     # and has no resolution -> caught


def test_dm_cluster_se_wider_than_naive():
    # 20 games x 30 highly-correlated within-game states, all positive diffs.
    rng = np.random.default_rng(0)
    d, clusters = [], []
    for g in range(20):
        base = 0.02 + 0.001 * rng.standard_normal()   # per-game effect dominates
        for _ in range(30):
            d.append(base + 1e-4 * rng.standard_normal())
            clusters.append(f"game{g}")
    clustered = diebold_mariano(d, clusters)
    naive = diebold_mariano(d, list(range(len(d))))   # each obs its own cluster
    # clustering must WIDEN the SE (within-game states are correlated). Compare
    # SE via CI half-width; p-values both floor at ~0 with this large effect, so
    # the SE is the honest property to assert.
    clustered_se = clustered.ci95[1] - clustered.ci95[0]
    naive_se = naive.ci95[1] - naive.ci95[0]
    assert clustered_se > naive_se, (clustered_se, naive_se)
    assert clustered.dm_stat < naive.dm_stat   # clustered is less "significant"
    assert clustered.n_clusters == 20 and naive.n_clusters == len(d)


def test_dm_rejects_cluster_length_mismatch():
    with pytest.raises(ValueError, match=r"cluster_ids length \(2\).*d length \(3\)"):
        diebold_mariano([0.1, 0.2, 0.3], ["g1", "g2"])


def test_dm_rejects_single_cluster():
    with pytest.raises(ValueError, match=r"at least 2 clusters.*got 1"):
        diebold_mariano([0.1, -0.1, 0.2], ["g1", "g1", "g1"])


def test_dm_uses_student_t_p_value():
    # Two one-observation clusters yield dm=1. With G-1=1, the Student-t
    # reference is Cauchy: two-tailed p = 1 - 2 * atan(1) / pi = 0.5.
    result = diebold_mariano([0.0, 2.0], ["g1", "g2"])
    expected = 1.0 - 2.0 * atan(1.0) / pi
    assert abs(result.dm_stat - 1.0) < 1e-12
    assert abs(result.p_value - expected) < 1e-12


def test_dm_happy_path_keeps_result_shape():
    result = diebold_mariano([0.0, 2.0, 1.0, 3.0], ["g1", "g1", "g2", "g2"])
    assert result.n == 4
    assert result.n_clusters == 2
    assert result.mean_diff == 1.5
    assert 0.0 <= result.p_value <= 1.0


def _valid_golden(n=90):
    regimes = ["pregame", "q4", "blowout", "foul_trouble", "q1", "q2", "q3"]
    states = []
    for i in range(n):
        states.append({
            "game_id": f"g{i}", "season": "2023-24", "sport": "nba",
            "regime": regimes[i % len(regimes)],
            "game_date": "2024-01-15", "state_ts": "2024-01-15T19:30:00",
            "features": {"x": 0.5}, "feature_avail": {"x": "2024-01-14T00:00:00"},
            "devig_close_prob": 0.55, "truth_wp": 0.55, "outcome": i % 2,
        })
    return states


def test_validate_golden_passes_on_valid_set():
    validate_golden(_valid_golden(90))   # should not raise


def test_validate_golden_fires_on_leak():
    bad = _valid_golden(90)
    bad[0]["feature_avail"]["x"] = "2024-01-16T00:00:00"   # AFTER state_ts -> leak
    try:
        validate_golden(bad)
        raise SystemExit("FAIL: leak not caught")
    except AssertionError as e:
        assert "LEAK" in str(e)


def test_validate_golden_fires_on_coverage_gap():
    bad = [s for s in _valid_golden(90) if s["regime"] != "foul_trouble"]
    # pad back to >=90 with an already-present regime so only coverage trips
    while len(bad) < 90:
        s = dict(bad[0]); s["game_id"] = f"pad{len(bad)}"; bad.append(s)
    try:
        validate_golden(bad)
        raise SystemExit("FAIL: coverage gap not caught")
    except AssertionError as e:
        assert "coverage gap" in str(e)


def test_crps_gaussian_reduces_to_mae_as_sigma_shrinks():
    # As sigma -> 0 a Gaussian predictive collapses to a point mass at mu, so
    # CRPS -> mean |mu - y| (MAE), not Brier (that identity is for the two-point
    # Bernoulli CDF, not this closed form).
    mu = np.array([100.0, 110.0, 95.0, 105.0])
    y = np.array([103.0, 108.0, 90.0, 105.0])
    tiny = np.full(4, 1e-6)
    mae = float(np.mean(np.abs(mu - y)))
    assert abs(crps_gaussian(mu, tiny, y) - mae) < 1e-3


def test_crps_gaussian_rewards_accurate_sharp():
    y = np.array([100.0, 110.0, 95.0, 105.0])
    accurate = crps_gaussian(y, np.full(4, 5.0), y)          # mean on target
    biased = crps_gaussian(y + 15.0, np.full(4, 5.0), y)     # systematically off
    assert accurate < biased


def test_crps_ensemble_matches_gaussian_samples():
    # An ensemble drawn from N(mu, sigma) should give ~ the closed-form CRPS.
    rng = np.random.default_rng(0)
    mu, sigma, n = 100.0, 8.0, 4000
    samples = mu + sigma * rng.standard_normal((1, n))
    y = np.array([103.0])
    emp = crps_ensemble(samples, y)
    closed = crps_gaussian([mu], [sigma], y)
    assert abs(emp - closed) < 0.5, (emp, closed)


def test_pinball_asymmetry_and_quantile_guard():
    y = np.array([10.0, 10.0])
    # for the 0.9 quantile, under-prediction is penalized ~9x harder than over.
    under = pinball_loss(y, np.full(2, 8.0), 0.9)
    over = pinball_loss(y, np.full(2, 12.0), 0.9)
    assert under > over
    assert abs(under - 0.9 * 2.0) < 1e-9 and abs(over - 0.1 * 2.0) < 1e-9
    try:
        pinball_loss(y, y, 1.5)
        raise SystemExit("FAIL: out-of-range quantile not caught")
    except ValueError:
        pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} eval-gate core tests passed.")
