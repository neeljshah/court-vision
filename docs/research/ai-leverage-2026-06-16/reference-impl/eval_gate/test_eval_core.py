"""Per-file tests for the eval-gate pure core (blueprint N1).

Runs standalone (`python test_eval_core.py`) OR under pytest. numpy + stdlib only.
Proves the math + the leak guard + the cluster-robust DM behavior the gate relies on.
"""
from __future__ import annotations
import numpy as np

from scoring import brier, log_loss, brier_skill_score, ece, resolution, sharpness
from dm_test import diebold_mariano
from schema import validate_golden


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


def _valid_golden(n=90):
    regimes = ["pregame", "q4", "blowout", "foul_trouble", "q1", "q2", "q3"]
    states = []
    for i in range(n):
        states.append({
            "game_id": f"g{i}", "season": "2023-24", "sport": "nba",
            "regime": regimes[i % len(regimes)],
            "game_date": "2024-01-15", "state_ts": "2024-01-15T19:30:00",
            "features": {"x": 0.5}, "feature_avail": {"x": "2024-01-14"},
            "devig_close_prob": 0.55, "truth_wp": 0.55, "outcome": i % 2,
        })
    return states


def test_validate_golden_passes_on_valid_set():
    validate_golden(_valid_golden(90))   # should not raise


def test_validate_golden_fires_on_leak():
    bad = _valid_golden(90)
    bad[0]["feature_avail"]["x"] = "2024-01-16"   # AFTER state_ts -> leak
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} eval-gate core tests passed.")
