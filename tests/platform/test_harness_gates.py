"""test_harness_gates.py — Acceptance tests for gates.py (gate behavior).

Python 3.9 compatible. No network. No subprocess to real pytest suite.
IMPORTANT: Do NOT call gates.record() (writes real build_state).
IMPORTANT: Do NOT call run_tier("wave") without mocking run_pytest / g1.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import gates  # noqa: E402


# ---------------------------------------------------------------------------
# 1. protected_scan
# ---------------------------------------------------------------------------

def test_protected_scan_exact_matches():
    result = gates.protected_scan(["CLAUDE.md", "kernel/x.py", "README.md"])
    assert "CLAUDE.md" in result and "README.md" in result
    assert "kernel/x.py" not in result


def test_protected_scan_exact_only_protected():
    assert set(gates.protected_scan(["CLAUDE.md", "kernel/x.py", "README.md"])) == {"CLAUDE.md", "README.md"}


def test_protected_scan_data_registry_prefix():
    assert "data/registry/STOP" in gates.protected_scan(["data/registry/STOP"])


def test_protected_scan_api_templates_prefix():
    assert "api/templates/index.html" in gates.protected_scan(["api/templates/index.html"])


def test_protected_scan_kernel_not_protected():
    assert gates.protected_scan(["kernel/x.py", "kernel/utils.py"]) == []


def test_protected_scan_empty_list():
    assert gates.protected_scan([]) == []


def test_protected_scan_unrelated_files():
    assert gates.protected_scan(["src/sim/basketball_sim.py", "tests/test_foo.py"]) == []


# ---------------------------------------------------------------------------
# 2. run_tier("task") — protected file → FAIL
# ---------------------------------------------------------------------------

def test_run_tier_task_protected_file_verdict_fail():
    result = gates.run_tier("task", task_files=["CLAUDE.md"])
    assert result["verdict"] == "FAIL"


def test_run_tier_task_protected_file_gate_details():
    result = gates.run_tier("task", task_files=["CLAUDE.md"])
    assert {g["gate"]: g["status"] for g in result["gates"]}.get("PROTECTED_SCAN") == "FAIL"


# ---------------------------------------------------------------------------
# 3. run_tier("task") — non-protected kernel file → PASS or PARTIAL
# ---------------------------------------------------------------------------

def test_run_tier_task_kernel_file_not_fail():
    result = gates.run_tier("task", task_files=["kernel/x.py"])
    assert result["verdict"] in {"PASS", "PARTIAL"}


def test_run_tier_task_kernel_file_ic_skips_when_absent():
    result = gates.run_tier("task", task_files=["kernel/x.py"])
    statuses = {g["gate"]: g["status"] for g in result["gates"]}
    assert statuses.get("PROTECTED_SCAN") == "PASS"
    ic = statuses.get("IC")
    if ic is not None:
        assert ic != "FAIL"


# ---------------------------------------------------------------------------
# 4. run_tier("phase") — UNAVAILABLE when no baselines/scripts (mocked)
# ---------------------------------------------------------------------------

def test_run_tier_phase_unavailable_in_h0(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "no_baseline.txt")
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)
    monkeypatch.setattr(gates, "run_pytest", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("run_pytest must NOT be called in this test")))
    result = gates.run_tier("phase", phase="0")
    assert result["verdict"] == "UNAVAILABLE"


def test_run_tier_phase_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "no_baseline.txt")
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)
    monkeypatch.setattr(gates, "run_pytest", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("run_pytest must NOT be called in this test")))
    result = gates.run_tier("phase", phase="0")
    assert result["tier"] == "phase" and "gates" in result and isinstance(result["gates"], list)


# ---------------------------------------------------------------------------
# 5. Structural checks
# ---------------------------------------------------------------------------

def test_run_tier_task_returns_tier_field():
    assert gates.run_tier("task", task_files=[])["tier"] == "task"


def test_run_tier_unknown_tier_fails():
    assert gates.run_tier("invalid_tier")["verdict"] == "FAIL"


def test_verdict_derivation_no_fail_all_skip():
    assert gates._verdict([{"gate": "G1", "status": "SKIP"}, {"gate": "G2", "status": "SKIP"}]) == "UNAVAILABLE"


def test_verdict_derivation_fail_present():
    assert gates._verdict([{"gate": "G1", "status": "PASS"}, {"gate": "G2", "status": "FAIL"}]) == "FAIL"


def test_verdict_derivation_all_pass():
    assert gates._verdict([{"gate": "G1", "status": "PASS"}, {"gate": "IC", "status": "PASS"}]) == "PASS"


def test_verdict_derivation_mixed_pass_skip():
    assert gates._verdict([{"gate": "G1", "status": "PASS"}, {"gate": "IC", "status": "SKIP"}]) == "PARTIAL"


# ---------------------------------------------------------------------------
# 6. run_pytest return-dict shape (mocked — no real subprocess)
# ---------------------------------------------------------------------------

def test_run_pytest_returns_elapsed_s_on_success(monkeypatch):
    import subprocess

    class _R:
        stdout = "1 passed\n"; stderr = ""; returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    res = gates.run_pytest(targets=["tests/platform/test_harness_gates.py"], timeout=10)
    assert res["ran"] is True and "elapsed_s" in res and isinstance(res["elapsed_s"], float)
    assert res["passed"] >= 1


def test_run_pytest_timed_out_flag(monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="pytest", timeout=1)))
    res = gates.run_pytest(targets=["tests/platform/test_harness_gates.py"], timeout=1)
    assert res["timed_out"] is True and res["ran"] is False
    assert "elapsed_s" in res and "error" in res


def test_run_pytest_timed_out_partial_output(monkeypatch):
    """TimeoutExpired.stdout is a property alias for .output; don't set .output after .stdout."""
    import subprocess

    def _raise(*a, **kw):
        exc = subprocess.TimeoutExpired(cmd="pytest", timeout=1)
        exc.stdout = "5 passed, 1 failed\n"  # writes through to exc.output via property setter
        raise exc

    monkeypatch.setattr(subprocess, "run", _raise)
    res = gates.run_pytest(targets=["tests/"], timeout=1)
    assert res["timed_out"] is True and res["passed"] == 5 and res["failed"] == 1


def test_run_pytest_other_exception_returns_timed_out_false(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("no pytest")))
    res = gates.run_pytest(targets=["tests/"], timeout=10)
    assert res["ran"] is False and res["timed_out"] is False and "elapsed_s" in res


# ---------------------------------------------------------------------------
# 7. G4 PASS with mocked fast run_pytest (budget = 420s, no real subprocess)
# ---------------------------------------------------------------------------

def test_g4_pass_when_run_pytest_passes(monkeypatch):
    monkeypatch.setattr(gates, "_script_exists", lambda rel: True)
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.05})
    result = gates.g4()
    assert result["status"] == "PASS" and result["gate"] == "G4"


def test_g4_timeout_falls_back_to_skip(monkeypatch):
    monkeypatch.setattr(gates, "_script_exists", lambda rel: True)
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": False, "timed_out": True, "error": "timed out after 420s",
        "elapsed_s": 420.0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0})
    assert gates.g4()["status"] == "SKIP"


# ---------------------------------------------------------------------------
# 8. Timed-out G1 with baseline present → FAIL (phase may not close on vacuous gate)
# ---------------------------------------------------------------------------

def test_g1_timeout_with_baseline_is_fail(monkeypatch, tmp_path):
    baseline = tmp_path / "pytest_baseline.txt"
    baseline.write_text("passed=10\nfailed=0\nskipped=0\nerrors=0\n")
    monkeypatch.setattr(gates, "PYTEST_BASELINE", baseline)
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": False, "timed_out": True, "error": "timed out after 1800s",
        "elapsed_s": 1800.0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0})
    result = gates.g1()
    assert result["status"] == "FAIL" and result.get("timed_out") is True


# ---------------------------------------------------------------------------
# 9. Wave tier — baseline absent → G1 SKIP with P0-H-005 reason (no full suite run)
# ---------------------------------------------------------------------------

def test_wave_tier_baseline_absent_g1_skips(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "no_baseline.txt")
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)
    monkeypatch.setattr(gates, "run_pytest", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("run_pytest must NOT be called at wave tier when baseline absent")))
    result = gates.run_tier("wave")
    statuses = {g["gate"]: g["status"] for g in result["gates"]}
    assert statuses.get("G1") == "SKIP"
    g1_gate = next(g for g in result["gates"] if g["gate"] == "G1")
    assert "P0-H-005" in g1_gate.get("why", "")
    assert not (tmp_path / "no_baseline.txt").exists()


def test_wave_tier_baseline_absent_verdict_not_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "no_baseline.txt")
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)
    monkeypatch.setattr(gates, "run_pytest", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("run_pytest must NOT be called at wave tier when baseline absent")))
    assert gates.run_tier("wave")["verdict"] != "FAIL"


# ---------------------------------------------------------------------------
# 10. NBA_OFFLINE env and pytest-timeout args injected
# ---------------------------------------------------------------------------

def test_run_pytest_sets_nba_offline(monkeypatch):
    import subprocess
    captured = {}

    class _R:
        stdout = "1 passed\n"; stderr = ""; returncode = 0

    def _cap(cmd, **kw):
        captured["env"] = kw.get("env", {})
        return _R()

    monkeypatch.setattr(subprocess, "run", _cap)
    gates.run_pytest(targets=["tests/platform/test_harness_gates.py"], timeout=10)
    assert captured["env"].get("NBA_OFFLINE") == "1"


def test_run_pytest_timeout_args_when_available(monkeypatch):
    import subprocess
    captured = {}

    class _R:
        stdout = "1 passed\n"; stderr = ""; returncode = 0

    def _cap(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(subprocess, "run", _cap)
    monkeypatch.setattr(gates, "_PYTEST_TIMEOUT_AVAILABLE", True)
    gates.run_pytest(targets=["tests/platform/test_harness_gates.py"], timeout=10)
    assert "--timeout=300" in captured["cmd"] and "--timeout-method=thread" in captured["cmd"]


def test_run_pytest_no_timeout_args_when_unavailable(monkeypatch):
    import subprocess
    captured = {}

    class _R:
        stdout = "1 passed\n"; stderr = ""; returncode = 0

    def _cap(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(subprocess, "run", _cap)
    monkeypatch.setattr(gates, "_PYTEST_TIMEOUT_AVAILABLE", False)
    gates.run_pytest(targets=["tests/platform/test_harness_gates.py"], timeout=10)
    assert "--timeout=300" not in captured["cmd"] and "--timeout-method=thread" not in captured["cmd"]
