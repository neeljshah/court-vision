"""test_harness_gates.py — Acceptance tests for gates.py (gate behavior).

Python 3.9 compatible. No network. No subprocess to real pytest suite.
IMPORTANT: Do NOT call gates.record() (writes real build_state).
IMPORTANT: Do NOT call run_tier("wave") (runs full pytest suite).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import gates  # noqa: E402


# ---------------------------------------------------------------------------
# 1. protected_scan: exact and prefix matches.
# ---------------------------------------------------------------------------

def test_protected_scan_exact_matches():
    result = gates.protected_scan(["CLAUDE.md", "kernel/x.py", "README.md"])
    assert "CLAUDE.md" in result, "CLAUDE.md should be protected"
    assert "README.md" in result, "README.md should be protected"
    assert "kernel/x.py" not in result, "kernel/x.py should NOT be protected"


def test_protected_scan_exact_only_protected():
    result = gates.protected_scan(["CLAUDE.md", "kernel/x.py", "README.md"])
    assert set(result) == {"CLAUDE.md", "README.md"}


def test_protected_scan_data_registry_prefix():
    result = gates.protected_scan(["data/registry/STOP"])
    assert "data/registry/STOP" in result, "data/registry/ prefix should be protected"


def test_protected_scan_api_templates_prefix():
    result = gates.protected_scan(["api/templates/index.html"])
    assert "api/templates/index.html" in result, "api/templates/ prefix should be protected"


def test_protected_scan_kernel_not_protected():
    result = gates.protected_scan(["kernel/x.py", "kernel/utils.py"])
    assert result == [], f"kernel/ files should NOT be protected, got {result}"


def test_protected_scan_empty_list():
    result = gates.protected_scan([])
    assert result == []


def test_protected_scan_unrelated_files():
    result = gates.protected_scan(["src/sim/basketball_sim.py", "tests/test_foo.py"])
    assert result == []


# ---------------------------------------------------------------------------
# 2. run_tier("task", protected file) → FAIL.
# ---------------------------------------------------------------------------

def test_run_tier_task_protected_file_verdict_fail():
    result = gates.run_tier("task", task_files=["CLAUDE.md"])
    assert result["verdict"] == "FAIL", (
        f"Protected file should cause FAIL verdict, got {result['verdict']}"
    )


def test_run_tier_task_protected_file_gate_details():
    result = gates.run_tier("task", task_files=["CLAUDE.md"])
    gate_statuses = {g["gate"]: g["status"] for g in result["gates"]}
    assert gate_statuses.get("PROTECTED_SCAN") == "FAIL"


# ---------------------------------------------------------------------------
# 3. run_tier("task", non-protected kernel file) → PASS or PARTIAL (not FAIL).
# ---------------------------------------------------------------------------

def test_run_tier_task_kernel_file_not_fail():
    result = gates.run_tier("task", task_files=["kernel/x.py"])
    assert result["verdict"] in {"PASS", "PARTIAL"}, (
        f"kernel/x.py task should not FAIL, got {result['verdict']}"
    )
    assert result["verdict"] != "FAIL"


def test_run_tier_task_kernel_file_ic_skips_when_absent():
    """IC skips if the script doesn't exist yet — this is the H0 behavior."""
    result = gates.run_tier("task", task_files=["kernel/x.py"])
    gate_statuses = {g["gate"]: g["status"] for g in result["gates"]}
    # PROTECTED_SCAN should be PASS, IC may be SKIP (script absent in H0)
    assert gate_statuses.get("PROTECTED_SCAN") == "PASS"
    # IC is expected to SKIP in H0 (script absent) but must never FAIL here
    ic_status = gate_statuses.get("IC")
    if ic_status is not None:
        assert ic_status != "FAIL", f"IC should SKIP (not FAIL) when script absent, got {ic_status}"


# ---------------------------------------------------------------------------
# 4. run_tier("phase", phase="0") → UNAVAILABLE (no baselines/scripts in H0).
# ---------------------------------------------------------------------------

def test_run_tier_phase_unavailable_in_h0():
    result = gates.run_tier("phase", phase="0")
    assert result["verdict"] == "UNAVAILABLE", (
        f"Phase tier should be UNAVAILABLE in H0 (no baselines), got {result['verdict']}"
    )


def test_run_tier_phase_structure():
    result = gates.run_tier("phase", phase="0")
    assert result["tier"] == "phase"
    assert "gates" in result
    assert isinstance(result["gates"], list)


# ---------------------------------------------------------------------------
# 5. Additional structural checks.
# ---------------------------------------------------------------------------

def test_run_tier_task_returns_tier_field():
    result = gates.run_tier("task", task_files=[])
    assert result["tier"] == "task"


def test_run_tier_unknown_tier_fails():
    result = gates.run_tier("invalid_tier")
    assert result["verdict"] == "FAIL"


def test_verdict_derivation_no_fail_all_skip():
    """_verdict on all-SKIP gates → UNAVAILABLE."""
    all_skip = [{"gate": "G1", "status": "SKIP"}, {"gate": "G2", "status": "SKIP"}]
    # Access private helper via the module
    verdict = gates._verdict(all_skip)
    assert verdict == "UNAVAILABLE"


def test_verdict_derivation_fail_present():
    gates_list = [{"gate": "G1", "status": "PASS"}, {"gate": "G2", "status": "FAIL"}]
    assert gates._verdict(gates_list) == "FAIL"


def test_verdict_derivation_all_pass():
    gates_list = [{"gate": "G1", "status": "PASS"}, {"gate": "IC", "status": "PASS"}]
    assert gates._verdict(gates_list) == "PASS"


def test_verdict_derivation_mixed_pass_skip():
    gates_list = [{"gate": "G1", "status": "PASS"}, {"gate": "IC", "status": "SKIP"}]
    assert gates._verdict(gates_list) == "PARTIAL"
