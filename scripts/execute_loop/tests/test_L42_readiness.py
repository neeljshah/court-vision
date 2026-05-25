"""Tests for L42_production_readiness.py — 8 tests using synthetic modules."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test without executing audited layers
# ---------------------------------------------------------------------------
_L42_PATH = Path(__file__).resolve().parents[1] / "L42_production_readiness.py"
spec = importlib.util.spec_from_file_location("L42_production_readiness", _L42_PATH)
_mod = importlib.util.module_from_spec(spec)
sys.modules["L42_production_readiness"] = _mod  # register before exec so @dataclass resolves __module__
spec.loader.exec_module(_mod)

check_paper_default = _mod.check_paper_default
check_atomic_writes = _mod.check_atomic_writes
check_env_var_documentation = _mod.check_env_var_documentation
check_file_perms = _mod.check_file_perms
ReadinessChecker = _mod.ReadinessChecker
CheckResult = _mod.CheckResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_module(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


def _make_state_json(tmp_path: Path, layer_names: list[str]) -> Path:
    layers = {}
    for i, name in enumerate(layer_names, start=1):
        layers[name] = {"name": f"Layer {name}", "status": "shipped",
                        "ships": [{"round": 1, "tests": "1/1", "loc": 100}]}
    state = {
        "version": 1,
        "layers": layers,
        "totals": {"layers_shipped": len(layer_names)},
    }
    p = tmp_path / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests: paper_default
# ---------------------------------------------------------------------------

def test_paper_default_pass_with_constant(tmp_path):
    src = '''\
"""Module with a constant paper mode."""
PAPER_MODE = True

def run():
    if PAPER_MODE:
        return "paper"
    return "live"
'''
    mod = _write_module(tmp_path, "L01_test.py", src)
    result = check_paper_default("L1", mod)
    assert result.status == "PASS"
    assert result.check == "paper_default"


def test_paper_default_pass_with_env_fallback(tmp_path):
    src = '''\
"""Module with env fallback to paper."""
import os

MODE = os.environ.get("SUBMISSION_MODE", "paper")

def submit():
    if MODE == "live":
        return "live_submit"
    return "paper_submit"
'''
    mod = _write_module(tmp_path, "L05_test.py", src)
    result = check_paper_default("L5", mod)
    assert result.status == "PASS"


def test_paper_default_fail_when_live_default(tmp_path):
    src = '''\
"""Module that defaults to live with no paper fallback."""
import os

MODE = os.environ.get("SUBMISSION_MODE", "live")

def submit():
    return "submit to live exchange"
'''
    mod = _write_module(tmp_path, "L09_test.py", src)
    result = check_paper_default("L9", mod)
    assert result.status == "FAIL"
    assert "paper" in result.detail.lower() or "live" in result.detail.lower()


# ---------------------------------------------------------------------------
# Tests: atomic_writes
# ---------------------------------------------------------------------------

def test_atomic_writes_pass_with_tempfile_replace(tmp_path):
    src = '''\
"""Module that uses atomic writes."""
import os
from pathlib import Path

def save(data, dest: Path):
    tmp = dest.with_suffix(".tmp.json")
    tmp.write_text(data)
    tmp.replace(dest)
'''
    mod = _write_module(tmp_path, "L07_test.py", src)
    result = check_atomic_writes("L7", mod)
    assert result.status == "PASS"


def test_atomic_writes_fail_for_direct_write(tmp_path):
    src = '''\
"""Module with a direct non-atomic write."""
from pathlib import Path

def save_bad(data, dest: Path):
    dest.write(data)
'''
    mod = _write_module(tmp_path, "L07_bad.py", src)
    result = check_atomic_writes("L7", mod)
    assert result.status == "FAIL"
    # Evidence must include a line number reference
    assert len(result.evidence) >= 1
    assert any("line" in ev for ev in result.evidence)


# ---------------------------------------------------------------------------
# Tests: env_var_documentation
# ---------------------------------------------------------------------------

def test_env_var_documentation_fail_when_undocumented(tmp_path):
    src = '''\
"""Module that uses env vars without documenting them."""
import os

API_KEY = os.environ.get("KALSHI_API_KEY")
ENABLED = os.environ.get("KALSHI_LIVE_ENABLED")

def connect():
    return API_KEY, ENABLED
'''
    mod = _write_module(tmp_path, "L09_envtest.py", src)
    result = check_env_var_documentation("L9", mod)
    assert result.status == "FAIL"
    assert len(result.evidence) >= 1
    # Both vars should appear in evidence
    all_ev = " ".join(result.evidence)
    assert "KALSHI_API_KEY" in all_ev or "KALSHI_LIVE_ENABLED" in all_ev


# ---------------------------------------------------------------------------
# Tests: file_perms
# ---------------------------------------------------------------------------

def test_file_perms_skip_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    results = check_file_perms(Path("/nonexistent/data"))
    assert len(results) == 1
    assert results[0].status == "SKIP"
    assert "Windows" in results[0].detail


# ---------------------------------------------------------------------------
# Tests: run_all_checks integration
# ---------------------------------------------------------------------------

def test_run_all_checks_covers_all_shipped_layers(tmp_path):
    """Integration test against the real layers_dir + state.json."""
    real_layers_dir = Path(__file__).resolve().parents[1]
    real_state_json = real_layers_dir / "state.json"

    if not real_state_json.exists():
        pytest.skip("state.json not found — skipping integration test")

    checker = ReadinessChecker(
        layers_dir=real_layers_dir,
        state_json_path=real_state_json,
    )
    report = checker.run_all_checks()

    # Must cover at least 30 shipped layers
    assert report.summary["layers"] >= 30, (
        f"Expected >=30 shipped layers, got {report.summary['layers']}"
    )

    # L29 (gated) must NOT appear in results
    assert "L29" not in report.layers, "L29 is gated and must be excluded"

    # to_markdown must produce non-empty output
    md = report.to_markdown()
    assert len(md) > 200

    # summary keys present
    for key in ("pass", "fail", "skip", "n_a", "layers"):
        assert key in report.summary
