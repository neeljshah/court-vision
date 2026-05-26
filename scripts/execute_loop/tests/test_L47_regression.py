"""test_L47_regression.py — Tests for L47_regression_detector.py.

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L47_regression.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).resolve().parent
_EL_DIR = _TESTS_DIR.parent
_PROJECT_DIR = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

from scripts.execute_loop.L47_regression_detector import (
    Regression,
    RegressionDetector,
    RegressionReport,
    detect_missing_modules,
    detect_orphan_tests,
    detect_ship_without_round,
    detect_test_count_drops,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_state(layers: dict) -> dict:
    """Build a minimal state.json dict with the given layers block."""
    return {
        "version": 2,
        "rounds_completed": 1,
        "layers": layers,
        "round_summaries": [],
        "totals": {},
    }


# ---------------------------------------------------------------------------
# Test 1 — test_count_drop: numerator falls → P0
# ---------------------------------------------------------------------------
def test_test_count_drop_detection():
    """v1 12/12 → v2 11/12 should be flagged as test_count_drop P0."""
    state = _minimal_state({
        "L99": {
            "name": "Fake layer",
            "status": "shipped",
            "ships": [
                {"round": 1, "tests": "12/12"},
                {"round": 2, "tests": "11/12"},
            ],
        }
    })
    regressions = detect_test_count_drops(state)
    assert len(regressions) == 1
    r = regressions[0]
    assert r.layer == "L99"
    assert r.category == "test_count_drop"
    assert r.severity == "P0"
    assert "12/12" in r.detail and "11/12" in r.detail
    assert r.from_round == 1
    assert r.to_round == 2


# ---------------------------------------------------------------------------
# Test 2 — no regression when counts are equal
# ---------------------------------------------------------------------------
def test_no_regression_when_counts_equal():
    """v1 10/10 → v2 10/10 should produce no flags."""
    state = _minimal_state({
        "L99": {
            "name": "Stable layer",
            "status": "shipped",
            "ships": [
                {"round": 1, "tests": "10/10"},
                {"round": 2, "tests": "10/10"},
            ],
        }
    })
    regressions = detect_test_count_drops(state)
    assert regressions == []


# ---------------------------------------------------------------------------
# Test 3 — test count INCREASE should not flag
# ---------------------------------------------------------------------------
def test_test_count_increase_no_flag():
    """v1 10/10 → v2 12/12 should produce no flags (more tests is healthy)."""
    state = _minimal_state({
        "L99": {
            "name": "Growing layer",
            "status": "shipped",
            "ships": [
                {"round": 1, "tests": "10/10"},
                {"round": 2, "tests": "12/12"},
            ],
        }
    })
    regressions = detect_test_count_drops(state)
    assert regressions == []


# ---------------------------------------------------------------------------
# Test 4 — missing module detected
# ---------------------------------------------------------------------------
def test_missing_module_detected(tmp_path: Path):
    """Shipped L99 with no L99_*.py file in layers_dir → missing_module P0."""
    # Create a layers dir with NO L99 file
    layers_dir = tmp_path / "execute_loop"
    layers_dir.mkdir()
    # Create an unrelated file to confirm the dir is non-empty
    (layers_dir / "L01_slate_ingester.py").write_text("# stub")

    state = _minimal_state({
        "L99": {
            "name": "Ghost layer",
            "status": "shipped",
            "ships": [{"round": 1, "tests": "5/5"}],
        }
    })
    regressions = detect_missing_modules(state, layers_dir)
    assert len(regressions) == 1
    r = regressions[0]
    assert r.layer == "L99"
    assert r.category == "missing_module"
    assert r.severity == "P0"


# ---------------------------------------------------------------------------
# Test 5 — orphan tests detected (shipped layer with tests but no test file)
# ---------------------------------------------------------------------------
def test_orphan_tests_detected(tmp_path: Path):
    """L88 shipped with 5/5 tests but no test_L88_*.py → missing_tests P1."""
    layers_dir = tmp_path / "execute_loop"
    layers_dir.mkdir()
    # Create the module file so missing_module doesn't also fire
    (layers_dir / "L88_fake_module.py").write_text("# stub")
    # Create tests dir but with no L88 test file
    tests_dir = layers_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_L01_slate.py").write_text("# unrelated")

    state = _minimal_state({
        "L88": {
            "name": "Orphaned layer",
            "status": "shipped",
            "ships": [{"round": 1, "tests": "5/5"}],
        }
    })
    regressions = detect_orphan_tests(state, layers_dir)
    assert len(regressions) == 1
    r = regressions[0]
    assert r.layer == "L88"
    assert r.category == "missing_tests"
    assert r.severity == "P1"
    assert "5" in r.detail


# ---------------------------------------------------------------------------
# Test 6 — gated layer must NOT produce missing_module flag
# ---------------------------------------------------------------------------
def test_gated_layer_not_flagged(tmp_path: Path):
    """L29 is gated — detect_missing_modules must skip it entirely."""
    layers_dir = tmp_path / "execute_loop"
    layers_dir.mkdir()
    # No L29 file exists
    state = _minimal_state({
        "L29": {
            "name": "Multi-account orchestrator",
            "status": "gated",
            "gated_reason": "requires explicit user auth",
        }
    })
    regressions = detect_missing_modules(state, layers_dir)
    assert regressions == []


# ---------------------------------------------------------------------------
# Test 7 — main CLI returns 1 under --strict when P0 present
# ---------------------------------------------------------------------------
def test_main_cli_exit_strict(tmp_path: Path):
    """main(['detect','--strict']) returns 1 when there is a P0 regression."""
    # Build a state.json where L77 is shipped but L77 module is absent
    layers_dir = tmp_path / "execute_loop"
    layers_dir.mkdir()
    (layers_dir / "tests").mkdir()

    state_data = _minimal_state({
        "L77": {
            "name": "Missing module layer",
            "status": "shipped",
            "ships": [{"round": 1, "tests": "3/3"}],
        }
    })
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state_data), encoding="utf-8")

    exit_code = main([
        "detect",
        "--strict",
        "--state", str(state_path),
        "--layers-dir", str(layers_dir),
    ])
    assert exit_code == 1
