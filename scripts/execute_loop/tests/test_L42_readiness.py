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
ReadinessReport = _mod.ReadinessReport
LayerKPI = _mod.LayerKPI


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


# ---------------------------------------------------------------------------
# Tests: atomic_writes v2 — helper-delegation and exempt writes
# ---------------------------------------------------------------------------

def test_atomic_writes_pass_with_helper_call(tmp_path):
    """Call site delegates to _atomic_write_json which contains os.replace — must PASS."""
    src = '''\
"""Module that defines an atomic helper and calls it."""
import json
import os
import tempfile
from pathlib import Path

def _atomic_write_json(path, payload):
    """Write payload atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, str(path))
    except Exception:
        os.unlink(tmp)
        raise

def save_queue(items, dest: Path):
    _atomic_write_json(dest, items)
'''
    mod = _write_module(tmp_path, "L22_test.py", src)
    result = check_atomic_writes("L22", mod)
    assert result.status == "PASS", f"Expected PASS, got FAIL: {result.evidence}"


def test_atomic_writes_exempts_wfile_write(tmp_path):
    """self.wfile.write(...) inside an HTTP handler should be exempt — must PASS."""
    src = '''\
"""HTTP handler module."""
from http.server import BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"hello"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)
'''
    mod = _write_module(tmp_path, "L23_test.py", src)
    result = check_atomic_writes("L23", mod)
    assert result.status == "PASS", f"Expected PASS, got FAIL: {result.evidence}"


def test_atomic_writes_exempts_stdout_write(tmp_path):
    """sys.stdout.write(...) is not a file write — must PASS."""
    src = '''\
"""Module writing only to stdout."""
import sys

def emit(msg: str) -> None:
    sys.stdout.write(msg + "\\n")
'''
    mod = _write_module(tmp_path, "L24_test.py", src)
    result = check_atomic_writes("L24", mod)
    assert result.status == "PASS", f"Expected PASS, got FAIL: {result.evidence}"


# ---------------------------------------------------------------------------
# Tests: paper_default v2 — prose-only 'live' and runtime branch
# ---------------------------------------------------------------------------

def test_paper_default_pass_when_live_only_in_docstring(tmp_path):
    """'live' appears only in docstrings/comments — should be N/A or PASS, never FAIL."""
    src = '''\
"""Module that compares model predictions against live exchange quotes.

No live HTTP calls are ever made; this is a pure computation module.
"""

def find_opportunities(predictions, quotes):
    """Evaluate edge vs live quotes from snapshot CSV (no live HTTP)."""
    results = []
    for q in quotes:
        results.append(q)
    return results
'''
    mod = _write_module(tmp_path, "L13_test.py", src)
    result = check_paper_default("L13", mod)
    assert result.status in ("PASS", "N/A"), (
        f"Expected PASS or N/A for prose-only 'live', got {result.status}: {result.detail}"
    )


def test_paper_default_fail_when_live_in_runtime_branch(tmp_path):
    """'live' used in a runtime if-branch with no paper default — must FAIL."""
    src = '''\
"""Module that branches on a live/paper mode at runtime."""
import os

MODE = os.environ.get("SUBMISSION_MODE", "live")

def submit(order):
    if MODE == "live":
        return _send_live(order)
    return None

def _send_live(order):
    pass
'''
    mod = _write_module(tmp_path, "L16_test.py", src)
    result = check_paper_default("L16", mod)
    assert result.status == "FAIL", (
        f"Expected FAIL for runtime live branch, got {result.status}"
    )


# ---------------------------------------------------------------------------
# Tests: KPI scoring — LayerKPI + compute_layer_kpis + kpi_summary_markdown
# ---------------------------------------------------------------------------

def _make_report_with_results(layers_results: dict) -> "ReadinessReport":
    """Build a ReadinessReport from a dict of layer -> list[CheckResult]."""
    from datetime import datetime, timezone
    counts: dict = {"pass": 0, "fail": 0, "skip": 0, "n_a": 0}
    for results in layers_results.values():
        for r in results:
            key = r.status.lower()
            if key == "n/a":
                counts["n_a"] += 1
            elif key in counts:
                counts[key] += 1
    # exclude 'global' from shipped count
    shipped = [k for k in layers_results if k != "global"]
    counts["layers"] = len(shipped)
    return ReadinessReport(
        layers=layers_results,
        summary=counts,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def test_compute_layer_kpis_basic(tmp_path):
    """Mixed PASS/FAIL/SKIP/N/A results → correct counts and stability_score."""
    state = {
        "version": 2,
        "layers": {
            "L1": {"name": "Ingester", "status": "shipped",
                   "ships": [{"round": 1, "tests": "5/5"}]},
            "L2": {"name": "Optimizer", "status": "shipped",
                   "ships": [{"round": 1, "tests": "3/3"},
                              {"round": 2, "version": 2, "tests": "6/6"}]},
        },
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    layers = {
        # L1: 1 PASS, 1 FAIL, 1 SKIP, 1 N/A → total=2, pass=1, fail=1, score=50.0
        "L1": [
            CheckResult("L1", "paper_default", "PASS", "ok"),
            CheckResult("L1", "atomic_writes", "FAIL", "bad write"),
            CheckResult("L1", "env_var_docs", "SKIP", "unreadable"),
            CheckResult("L1", "extra_check", "N/A", "not applicable"),
        ],
        # L2: 2 PASS → total=2, score=100.0
        "L2": [
            CheckResult("L2", "paper_default", "PASS", "ok"),
            CheckResult("L2", "atomic_writes", "PASS", "ok"),
        ],
    }
    report = _make_report_with_results(layers)
    kpis = report.compute_layer_kpis(state_path)

    assert "L1" in kpis and "L2" in kpis
    k1 = kpis["L1"]
    assert k1.checks_total == 2
    assert k1.checks_pass == 1
    assert k1.checks_fail == 1
    assert k1.stability_score == 50.0
    assert k1.v1_tests == "5/5"
    assert k1.v2_tests is None
    assert k1.ships == 1

    k2 = kpis["L2"]
    assert k2.checks_total == 2
    assert k2.checks_pass == 2
    assert k2.stability_score == 100.0
    assert k2.v1_tests == "3/3"
    assert k2.v2_tests == "6/6"
    assert k2.ships == 2


def test_stability_score_skip_only_returns_100(tmp_path):
    """All SKIP/N/A checks → stability_score == 100.0."""
    state = {"version": 2, "layers": {
        "L5": {"name": "Skipper", "status": "shipped",
               "ships": [{"round": 1, "tests": "2/2"}]},
    }}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    layers = {
        "L5": [
            CheckResult("L5", "paper_default", "SKIP", "unreadable"),
            CheckResult("L5", "atomic_writes", "N/A", "no writes"),
        ],
    }
    report = _make_report_with_results(layers)
    kpis = report.compute_layer_kpis(state_path)
    assert kpis["L5"].stability_score == 100.0
    assert kpis["L5"].checks_total == 0


def test_stability_score_all_fail_returns_zero(tmp_path):
    """All FAIL checks → stability_score == 0.0."""
    state = {"version": 2, "layers": {
        "L9": {"name": "Failing Layer", "status": "shipped",
               "ships": [{"round": 1, "tests": "0/5"}]},
    }}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    layers = {
        "L9": [
            CheckResult("L9", "paper_default", "FAIL", "no paper"),
            CheckResult("L9", "atomic_writes", "FAIL", "bad writes"),
            CheckResult("L9", "env_var_docs", "FAIL", "undocumented"),
        ],
    }
    report = _make_report_with_results(layers)
    kpis = report.compute_layer_kpis(state_path)
    assert kpis["L9"].stability_score == 0.0
    assert kpis["L9"].checks_fail == 3


def test_kpi_summary_markdown_includes_all_layers(tmp_path):
    """Integration: real state.json → every shipped layer appears in markdown output."""
    real_layers_dir = Path(__file__).resolve().parents[1]
    real_state_json = real_layers_dir / "state.json"
    if not real_state_json.exists():
        pytest.skip("state.json not found — skipping integration test")

    checker = ReadinessChecker(layers_dir=real_layers_dir, state_json_path=real_state_json)
    report = checker.run_all_checks()
    kpis = report.compute_layer_kpis(real_state_json)
    md = report.kpi_summary_markdown(kpis)

    # Every layer in the KPI dict must appear in the table
    for layer in kpis:
        assert layer in md, f"Layer {layer} missing from kpi_summary_markdown output"

    # Sanity: must have a header row and at least one data row
    assert "| Layer |" in md
    assert "Stability" in md


def test_kpi_cli_writes_json(tmp_path):
    """kpi --json <path> creates a valid JSON file with expected keys."""
    real_layers_dir = Path(__file__).resolve().parents[1]
    real_state_json = real_layers_dir / "state.json"
    if not real_state_json.exists():
        pytest.skip("state.json not found — skipping integration test")

    out_path = tmp_path / "kpi_out.json"
    # Call _cli directly via the module (argv injection)
    _cli = _mod._cli
    _cli(["kpi", "--json", str(out_path)])

    assert out_path.exists(), "JSON output file was not created"
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(payload) > 0, "KPI JSON payload is empty"

    # Pick a known shipped layer and check required keys exist
    first_key = next(iter(payload))
    first_kpi = payload[first_key]
    for key in ("layer", "name", "checks_total", "checks_pass", "checks_fail",
                "stability_score", "v1_tests", "v2_tests", "ships"):
        assert key in first_kpi, f"Missing key '{key}' in KPI JSON for {first_key}"
