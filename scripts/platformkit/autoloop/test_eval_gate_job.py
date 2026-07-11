"""Per-file test for scripts.platformkit.autoloop.eval_gate_job.

Acceptance criteria:
1. Artifact < 168h (7d) old -> skip, run_fn not called.
2. Artifact >= 168h old -> run_fn called, ops-json written.
3. No artifact at all -> treated as due, run_fn called.
4. run_fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here).
5. _default_run's sys.path shim: eval_gate/'s directory is on sys.path during
   the call and removed after (whether or not it was already present).
6. Registration: eval_gate_job appears in maintenance_templates._JOB_TABLE
   and _default_run is the only entry point that imports run_all (no argv to
   pass -- run_all.main() takes none, verified in the job's own docstring).
No real run_all.main() test-module run in the cadence/skip tests below.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_eval_gate_job.py -q
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from scripts.platformkit.autoloop import eval_gate_job as EG


def _touch_artifact(tmp_path, age_h):
    p = tmp_path / "eval_gate_scoreboard_latest.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def _fake_result(passed=38, total=38):
    return {"exit_code": 0 if passed == total else 1, "total_passed": passed,
           "total_tests": total,
           "modules": [{"module": "test_eval_core", "passed": passed, "total": total}]}


def test_fresh_artifact_skips_no_run_call(tmp_path):
    p = _touch_artifact(tmp_path, age_h=1.0)
    calls = []
    out = EG.run_eval_gate(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_artifact_runs_and_writes_ops_json(tmp_path):
    p = tmp_path / "eval_gate_scoreboard_latest.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - 200 * 3600, time.time() - 200 * 3600))
    calls = []
    out = EG.run_eval_gate(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert calls == ["run"]
    assert out["exit_code"] == 0
    assert out["total_passed"] == out["total_tests"] == 38
    assert p.exists()
    import json
    doc = json.loads(p.read_text(encoding="ascii"))
    assert doc["eval_gate_scoreboard"]["run_status"] == "ALL_GREEN"
    assert doc["eval_gate_scoreboard"]["total_passed"] == 38


def test_missing_artifact_treated_as_due(tmp_path):
    p = tmp_path / "eval_gate_scoreboard_latest.json"
    calls = []
    out = EG.run_eval_gate(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["run"]


def test_failures_present_written_honestly(tmp_path):
    p = tmp_path / "eval_gate_scoreboard_latest.json"
    out = EG.run_eval_gate(artifact_path=p, run_fn=lambda: _fake_result(passed=37, total=38))
    assert out["status"] == "ran"
    assert out["exit_code"] == 1
    import json
    doc = json.loads(p.read_text(encoding="ascii"))
    assert doc["eval_gate_scoreboard"]["run_status"] == "FAILURES_PRESENT"


def test_run_raise_propagates_uncaught(tmp_path):
    p = _touch_artifact(tmp_path, age_h=200.0)

    def _boom():
        raise RuntimeError("run_all boom")

    with pytest.raises(RuntimeError, match="run_all boom"):
        EG.run_eval_gate(artifact_path=p, run_fn=_boom)


def test_watermarks_param_accepted_and_ignored(tmp_path):
    """Call-shape uniformity with the other maintenance jobs -- watermarks
    is accepted positionally but never read or mutated."""
    p = _touch_artifact(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = EG.run_eval_gate(watermarks, artifact_path=p, run_fn=lambda: _fake_result())
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_run_sys_path_shim_added_and_removed(monkeypatch):
    """Regression guard for the bare-name-import shim: eval_gate/'s own dir
    must be on sys.path during the call (run_all.MODULES imports bare
    'test_eval_core' names, ModuleNotFoundError otherwise) and removed after,
    so the job never permanently pollutes sys.path across cycles."""
    eg_dir = str(EG._EVAL_GATE_DIR)
    assert eg_dir not in sys.path
    seen_during = {}

    class _FakeRA:
        MODULES = ["fake_mod_a", "fake_mod_b"]

        @staticmethod
        def run_module(name):
            seen_during["on_path"] = eg_dir in sys.path
            return (1, 1)

    monkeypatch.setitem(sys.modules, "scripts.platformkit.eval_gate.run_all", _FakeRA)
    result = EG._default_run()
    assert seen_during["on_path"] is True
    assert eg_dir not in sys.path
    assert result["total_passed"] == result["total_tests"] == 2


def test_default_run_no_argv_touched(monkeypatch):
    """run_all.main() (and the run_module() path this job calls instead)
    takes no arguments and never parses sys.argv -- documented in the job's
    module docstring as the reason no argv=[] guard is needed here, unlike
    M16's clv_refresh_job. This asserts sys.argv is untouched by the call."""
    before = list(sys.argv)
    monkeypatch.setattr(sys, "argv", ["m38_autoloop", "--interval", "86400"])

    class _FakeRA:
        MODULES = []

        @staticmethod
        def run_module(name):  # pragma: no cover -- MODULES empty, never called
            return (0, 0)

    monkeypatch.setitem(sys.modules, "scripts.platformkit.eval_gate.run_all", _FakeRA)
    EG._default_run()
    assert sys.argv == ["m38_autoloop", "--interval", "86400"]
    sys.argv = before


def test_registered_in_job_table():
    """_GOLDEN_KEYS itself (test_maintenance_templates.py's own regression
    guard) is updated there, not re-asserted here -- this test only checks
    this job's own _JOB_TABLE row shape."""
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "eval_gate" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "eval_gate")
    assert row[1] == "scripts.platformkit.autoloop.eval_gate_job"
    assert row[2] == "run_eval_gate"
    assert "watermarks" in row[3]
