"""Tests for fit_validity_gate.py -- the guard is the point.

Asserts:
    1. the pre-registration spec loads and its guard-relevant fields have
       the expected committed values (pre_registered=True, run_permitted=False).
    2. run_gate() ALWAYS raises FitGateNotAuthorized this wave, regardless of
       explicit_run_requested, because run_permitted is False in the
       committed spec.
    3. the planted-null/pure-noise stubs raise NotImplementedError rather
       than silently returning fabricated data.

Per-file only: python -m pytest scripts/platformkit/intel_validation/test_fit_validity_gate.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.intel_validation.fit_validity_gate import (
    FitGateNotAuthorized,
    PREREG_SPEC_PATH,
    load_prereg_spec,
    pure_noise_control,
    run_gate,
    shuffle_move_team_assignment,
)


def test_spec_loads_with_expected_guard_fields():
    spec = load_prereg_spec()
    assert spec.pre_registered is True
    assert spec.run_permitted is False
    assert spec.n_moves == 96
    assert spec.decision_current_wave.startswith("NOT_TESTABLE")


def test_spec_file_exists_at_documented_path():
    assert PREREG_SPEC_PATH.exists()
    assert PREREG_SPEC_PATH.name == "fit_validity_gate_prereg.json"


def test_run_gate_refuses_without_explicit_request():
    with pytest.raises(FitGateNotAuthorized, match="explicit_run_requested=False"):
        run_gate(explicit_run_requested=False)


def test_run_gate_refuses_even_with_explicit_request_because_run_not_permitted():
    with pytest.raises(FitGateNotAuthorized, match="run_permitted is False"):
        run_gate(explicit_run_requested=True)


def test_shuffle_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        shuffle_move_team_assignment(moves=None, seed=0)


def test_pure_noise_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        pure_noise_control(fit_scores=None, seed=0)


def test_missing_pre_registered_field_fails_closed(tmp_path):
    import json

    bad_spec = tmp_path / "bad_prereg.json"
    bad_spec.write_text(
        json.dumps({"run_permitted": False, "status": "x", "hypothesis": {"H1_candidate": "x"},
                    "corpus": {"verified_counts": {"n_strict_moves_team_changed": 0}},
                    "decision_rule": {"current_wave_verdict": "x"}}),
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="pre_registered"):
        load_prereg_spec(bad_spec)
