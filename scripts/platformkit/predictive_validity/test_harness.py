"""Per-file tests for scripts.platformkit.predictive_validity.harness --
SYNTHETIC fixtures only (this worktree has no data/ dir; real-data smokes run
post-merge against the real corpus).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_harness.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.predictive_validity.harness import MetricTest, run_metric_test

N_ENTITIES = 40
CUTOFFS = ["2024-01-01", "2024-02-01", "2024-03-01"]
N_FORWARD = [15] * N_ENTITIES
N_BOOT_FAST = 300  # a small n_boot below this makes the null-guard's CI too noisy (false positives rise)


def _test(metric_asof, baseline_asof, forward_outcome, cutoffs=None) -> MetricTest:
    return MetricTest(
        family="t_synth", sport="nba", metric_name="m", baseline_name="b",
        cutoffs=list(cutoffs or CUTOFFS), forward_games=20, min_forward_games=10,
        min_entities_per_fold=10, metric_asof=metric_asof, baseline_asof=baseline_asof,
        forward_outcome=forward_outcome,
    )


def test_perfect_predictor_is_verified():
    rng = np.random.default_rng(0)

    def metric_asof(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": np.arange(N_ENTITIES)})

    def baseline_asof(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": rng.permutation(N_ENTITIES)})

    def forward_outcome(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES),
                              "outcome": np.arange(N_ENTITIES),  # == metric, exactly rank-perfect
                              "n_forward": N_FORWARD})

    result = run_metric_test(_test(metric_asof, baseline_asof, forward_outcome), n_boot=N_BOOT_FAST)
    assert result["verdict"] == "PREDICTIVE_VERIFIED"
    assert result["mean_rho_metric"] > 0.99
    assert result["rho_metric_bootstrap"]["ci_lo"] > 0.9


def test_noise_metric_vs_decent_baseline_not_verified():
    rng = np.random.default_rng(1)

    def metric_asof(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": rng.permutation(N_ENTITIES)})

    def baseline_asof(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": np.arange(N_ENTITIES)})

    def forward_outcome(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES),
                              "outcome": np.arange(N_ENTITIES),  # baseline is rank-perfect, metric is noise
                              "n_forward": N_FORWARD})

    result = run_metric_test(_test(metric_asof, baseline_asof, forward_outcome), n_boot=N_BOOT_FAST)
    assert result["verdict"] != "PREDICTIVE_VERIFIED"
    assert result["verdict"] in ("DESCRIPTIVE_ONLY", "UNDERPOWERED")


def test_single_fold_is_underpowered():
    def metric_asof(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": np.arange(N_ENTITIES)})

    def forward_outcome(cutoff):
        return pd.DataFrame({"entity_id": range(N_ENTITIES), "outcome": np.arange(N_ENTITIES),
                              "n_forward": N_FORWARD})

    result = run_metric_test(
        _test(metric_asof, metric_asof, forward_outcome, cutoffs=[CUTOFFS[0]]), n_boot=N_BOOT_FAST)
    assert result["verdict"] == "UNDERPOWERED"
    assert result["n_folds"] <= 1


def test_all_folds_skipped_below_floor_is_underpowered():
    def empty(cutoff):
        return pd.DataFrame({"entity_id": [], "value": []})

    def empty_outcome(cutoff):
        return pd.DataFrame({"entity_id": [], "outcome": [], "n_forward": []})

    result = run_metric_test(_test(empty, empty, empty_outcome), n_boot=N_BOOT_FAST)
    assert result["verdict"] == "UNDERPOWERED"
    assert result["n_folds"] == 0
    assert all(f["status"] == "SKIPPED_BELOW_FLOOR" for f in result["per_cutoff"])


def test_shuffled_outcome_null_rarely_verified():
    """Leak-by-construction guard: with metric/baseline/outcome all
    independently shuffled (no real signal anywhere), PREDICTIVE_VERIFIED
    must be rare -- at most 1 pass across 20 independent shuffles."""
    passes = 0
    for seed in range(20):
        rng = np.random.default_rng(1000 + seed)

        def metric_asof(cutoff, rng=rng):
            return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": rng.permutation(N_ENTITIES)})

        def baseline_asof(cutoff, rng=rng):
            return pd.DataFrame({"entity_id": range(N_ENTITIES), "value": rng.permutation(N_ENTITIES)})

        def forward_outcome(cutoff, rng=rng):
            return pd.DataFrame({"entity_id": range(N_ENTITIES),
                                  "outcome": rng.permutation(N_ENTITIES), "n_forward": N_FORWARD})

        result = run_metric_test(_test(metric_asof, baseline_asof, forward_outcome), n_boot=N_BOOT_FAST)
        if result["verdict"] == "PREDICTIVE_VERIFIED":
            passes += 1
    assert passes <= 1
