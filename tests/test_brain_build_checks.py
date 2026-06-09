"""P0.3 — tests for the single-authority build-check (ARCHITECTURE.md §3).

Tests assert:
  - check_flag_registry() passes without raising.
  - run_all()["ok"] is True.
  - Weight authority report contains expected structural keys.
  - No weight-authority violations exist in the current source.
"""
from __future__ import annotations

import os
import sys

# Ensure src/ is importable (mirrors the other brain test files).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from brain.build_checks import (  # noqa: E402
    check_flag_registry,
    check_weight_authority,
    run_all,
)


# ---------------------------------------------------------------------------
# check_flag_registry
# ---------------------------------------------------------------------------

def test_check_flag_registry_passes() -> None:
    """check_flag_registry() must not raise on the current flags.py."""
    check_flag_registry()   # raises AssertionError on failure


def test_flag_registry_returns_none() -> None:
    """check_flag_registry() returns None (all-pass path)."""
    result = check_flag_registry()
    assert result is None


# ---------------------------------------------------------------------------
# check_weight_authority
# ---------------------------------------------------------------------------

def test_check_weight_authority_passes() -> None:
    """check_weight_authority() must not raise and return ok=True."""
    report = check_weight_authority()
    assert report["ok"] is True


def test_weight_authority_no_violations() -> None:
    """The violations list must be empty — no second brain-written weight JSON."""
    report = check_weight_authority()
    assert report["violations"] == [], (
        f"Unexpected weight-authority violations: {report['violations']}"
    )


def test_weight_authority_allowed_target_correct() -> None:
    """The allowed write target must be engine_reliability_weights.json."""
    report = check_weight_authority()
    assert report["allowed_write_target"] == "engine_reliability_weights.json"


def test_weight_authority_inputs_only_present() -> None:
    """The inputs_only list must contain the known INPUT-only filenames."""
    report = check_weight_authority()
    inputs = set(report["inputs_only"])
    assert "ensemble_weights_proposal.json" in inputs
    assert "brain_regime_weights.json" in inputs
    assert "reliability_export.json" in inputs


def test_weight_authority_legacy_data_files_is_list() -> None:
    """legacy_data_files must be a list (may be empty if data/ absent)."""
    report = check_weight_authority()
    assert isinstance(report["legacy_data_files"], list)


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------

def test_run_all_ok() -> None:
    """run_all() must return a dict with ok=True."""
    report = run_all()
    assert report["ok"] is True


def test_run_all_checks_sub_report() -> None:
    """run_all() must expose sub-reports for both checks."""
    report = run_all()
    assert "checks" in report
    checks = report["checks"]
    assert "flag_registry" in checks
    assert "weight_authority" in checks
    assert checks["flag_registry"]["ok"] is True
    assert checks["weight_authority"]["ok"] is True
