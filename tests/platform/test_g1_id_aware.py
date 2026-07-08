"""tests/platform/test_g1_id_aware.py -- P0-H-005 id-aware G1 gate.

Synthetic junit fixtures only.  run_pytest is monkeypatched -- the real suite
is NEVER invoked (per-file-only rule).  Do NOT call gates.record().
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import gates  # noqa: E402

JUNIT_BASE = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="5" errors="1" failures="1" skipped="1">
  <testcase classname="tests.foo.test_a" name="test_ok" time="0.01"/>
  <testcase classname="tests.foo.test_a" name="test_ok2" time="0.01"/>
  <testcase classname="tests.foo.test_a" name="test_frozen_fail" time="0.01">
    <failure message="AssertionError">assert False</failure>
  </testcase>
  <testcase classname="tests.foo.test_a" name="test_frozen_err" time="0.01">
    <error message="RuntimeError">boom</error>
  </testcase>
  <testcase classname="tests.foo.test_a" name="test_skip" time="0.0">
    <skipped message="r"/>
  </testcase>
</testsuite>
"""

JUNIT_NEW_FAILURE = JUNIT_BASE.replace(
    '<testcase classname="tests.foo.test_a" name="test_ok2" time="0.01"/>',
    '<testcase classname="tests.foo.test_a" name="test_ok2" time="0.01">'
    '<failure message="AssertionError">new break</failure></testcase>')

# Only 2 testcases collected (drop of 3 > tolerance would need >5; build a
# bigger baseline for the drop test instead).
JUNIT_DROPPED = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" errors="0" failures="0" skipped="0">
  <testcase classname="tests.foo.test_a" name="test_ok" time="0.01"/>
</testsuite>
"""


def _fake_run_pytest(junit_text):
    """Return a run_pytest stand-in that writes *junit_text* to junitxml."""
    def fake(targets=None, timeout=1800, junitxml=None):
        if junitxml:
            Path(junitxml).write_text(junit_text, encoding="utf-8")
        return {"ran": True, "timed_out": False, "rc": 1,
                "passed": 2, "failed": 1, "skipped": 1, "errors": 1,
                "elapsed_s": 0.1}
    return fake


def _point_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "pytest_baseline.txt")
    monkeypatch.setattr(gates, "G1_JUNIT", tmp_path / "junit.xml")


def _write_baseline(tmp_path, **over):
    base = {"captured_at": "2026-07-07T00:00:00", "partial": False,
            "passed": 2, "skipped": 1, "total_collected": 5,
            "failed_ids": ["tests.foo.test_a::test_frozen_fail"],
            "error_ids": ["tests.foo.test_a::test_frozen_err"]}
    base.update(over)
    (tmp_path / "pytest_baseline.txt").write_text(
        json.dumps(base), encoding="utf-8")
    return base


def test_recorded_writes_id_aware_baseline(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(gates, "run_pytest", _fake_run_pytest(JUNIT_BASE))
    out = gates.g1()
    assert out["status"] == "RECORDED"
    written = json.loads((tmp_path / "pytest_baseline.txt").read_text())
    assert written["failed_ids"] == ["tests.foo.test_a::test_frozen_fail"]
    assert written["error_ids"] == ["tests.foo.test_a::test_frozen_err"]
    assert written["total_collected"] == 5
    assert written["partial"] is False


def test_baseline_required_skips_when_absent(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    out = gates.g1(baseline_required=True)
    assert out["status"] == "SKIP"


def test_frozen_failures_pass(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    _write_baseline(tmp_path)
    monkeypatch.setattr(gates, "run_pytest", _fake_run_pytest(JUNIT_BASE))
    out = gates.g1(baseline_required=True)
    assert out["status"] == "PASS"
    assert out["frozen_excluded"] == 2


def test_new_failure_fails(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    _write_baseline(tmp_path)
    monkeypatch.setattr(gates, "run_pytest", _fake_run_pytest(JUNIT_NEW_FAILURE))
    out = gates.g1(baseline_required=True)
    assert out["status"] == "FAIL"
    assert "tests.foo.test_a::test_ok2" in out["why"]


def test_collected_drop_fails(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    # baseline says 20 collected; current junit has 1 -> drop 19 > tolerance 5
    _write_baseline(tmp_path, total_collected=20)
    monkeypatch.setattr(gates, "run_pytest", _fake_run_pytest(JUNIT_DROPPED))
    out = gates.g1(baseline_required=True)
    assert out["status"] == "FAIL"
    assert "dropped" in out["why"]


def test_partial_baseline_skips(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    _write_baseline(tmp_path, partial=True)
    out = gates.g1(baseline_required=True)
    assert out["status"] == "SKIP"
    assert "PARTIAL" in out["why"]


def test_legacy_counts_baseline_still_compares(monkeypatch, tmp_path):
    _point_paths(monkeypatch, tmp_path)
    (tmp_path / "pytest_baseline.txt").write_text(
        "passed=2\nfailed=0\nskipped=1\nerrors=0\n", encoding="utf-8")
    monkeypatch.setattr(gates, "run_pytest", _fake_run_pytest(JUNIT_BASE))
    out = gates.g1(baseline_required=True)
    # fake run reports failed=1/errors=1 -> legacy comparison must FAIL
    assert out["status"] == "FAIL"
    assert "legacy" in out.get("why", "")
