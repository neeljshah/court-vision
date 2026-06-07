"""Tests for the FINAL VERIFICATION harness (src.loop.joint_verification).

Each test asserts one of the three architectural guarantees with the same
self-contained synthetic data the harness uses. No network, no GPU, offline.

Run:
    python -m pytest tests/test_loop_joint_verification.py -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.loop.joint_verification import (  # noqa: E402
    proof_fdr_and_held_out_guard,
    proof_intel_leakfree_cvready_bridged,
    proof_redundant_second_signal,
    proof_reinforcement_end_to_end,
    proof_simulator_models_joint_correlation,
    run_all,
)


def test_joint_gate_discounts_redundant_second_signal():
    r = proof_redundant_second_signal(device="cpu")
    assert r.passed, r.detail
    d = r.detail
    # genuinely correlated
    assert d["observed_corr_s1_s2"] > 0.8
    # each is +EV alone (improves the FULL base)
    assert d["s1_alone_passes"] and d["s2_alone_passes"]
    assert d["ablation_delta_s1_alone"] < 0 and d["ablation_delta_s2_alone"] < 0
    # redundant together: the second's lift collapses once the first is present
    assert not d["s2_given_s1_passes"]
    assert d["s2_lift_survival_ratio"] < 0.1
    assert d["verdict_s1"] == "SHIP" and d["verdict_s2_given_s1"] != "SHIP"


def test_simulator_emits_joint_distribution():
    r = proof_simulator_models_joint_correlation(device="cpu")
    assert r.passed, r.detail
    assert r.detail["has_correlation_matrix"] is True
    assert r.detail["joint_model_prob"] is not None
    assert 0.0 <= r.detail["home_win_prob"] <= 1.0


def test_fdr_and_held_out_guard_enforced():
    r = proof_fdr_and_held_out_guard()
    assert r.passed, r.detail


def test_intel_leakfree_cvready_factory_bridged():
    r = proof_intel_leakfree_cvready_bridged(device="cpu")
    assert r.passed, r.detail
    assert r.detail["cv_slot_values_null_now"] is True
    assert r.detail["factory_not_rebuilt"] is True
    assert r.detail["leak_free_read_before_as_of_is_none"] is True


def test_reinforcement_end_to_end():
    r = proof_reinforcement_end_to_end()
    assert r.passed, r.detail
    assert r.detail["atlas_read_leak_safe"] is True
    assert r.detail["scanner_emits_atlas_signal"] is True
    assert r.detail["signal_write_back_ok"] is True


def test_run_all_passes():
    results = run_all(device="cpu")
    assert len(results) == 5
    assert all(r.passed for r in results.values()), {
        k: v.detail for k, v in results.items() if not v.passed}


if __name__ == "__main__":
    test_joint_gate_discounts_redundant_second_signal()
    test_simulator_emits_joint_distribution()
    test_fdr_and_held_out_guard_enforced()
    test_intel_leakfree_cvready_factory_bridged()
    test_reinforcement_end_to_end()
    test_run_all_passes()
    print("ALL JOINT-VERIFICATION TESTS PASSED")
