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

_CANNED_SCOPED_G1_PASS = [
    {"gate": "G1", "status": "PASS",
     "why": "scoped: 1 files, 1p 0f 0e in 0.0s", "selection": [], "elapsed_s": 0.01,
     "counts": {"passed": 1, "failed": 0, "skipped": 0, "errors": 0}},
    {"gate": "HERMETICITY", "status": "PASS", "tier": "task"},
]


def test_run_tier_task_kernel_file_not_fail(monkeypatch):
    monkeypatch.setattr(gates, "_scoped_g1",
                        lambda files, tier="task": list(_CANNED_SCOPED_G1_PASS))
    result = gates.run_tier("task", task_files=["kernel/x.py"])
    assert result["verdict"] in {"PASS", "PARTIAL"}


def test_run_tier_task_kernel_file_ic_skips_when_absent(monkeypatch):
    monkeypatch.setattr(gates, "_scoped_g1",
                        lambda files, tier="task": list(_CANNED_SCOPED_G1_PASS))
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

def test_run_tier_task_returns_tier_field(monkeypatch):
    monkeypatch.setattr(gates, "_scoped_g1",
                        lambda files, tier="task": list(_CANNED_SCOPED_G1_PASS))
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

_CANNED_SCOPED_G1_SKIP_H005 = [
    {"gate": "G1", "status": "SKIP",
     "why": "P0-H-005: baseline absent — scoped G1 runs only after P0-B-001 (pytest baseline) exists"},
    {"gate": "HERMETICITY", "status": "SKIP",
     "why": "G1 skipped — P0-H-005: baseline absent"},
]


def test_wave_tier_baseline_absent_g1_skips(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "PYTEST_BASELINE", tmp_path / "no_baseline.txt")
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)
    # Hermetic: mock _scoped_g1 so no real subprocess is spawned.
    # The canned result simulates the expected P0-H-005 skip reason.
    monkeypatch.setattr(gates, "_scoped_g1",
                        lambda *a, **kw: list(_CANNED_SCOPED_G1_SKIP_H005))
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
    # Hermetic: mock _scoped_g1 so no real subprocess is spawned.
    monkeypatch.setattr(gates, "_scoped_g1",
                        lambda *a, **kw: list(_CANNED_SCOPED_G1_SKIP_H005))
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


# ---------------------------------------------------------------------------
# 11. P0-H-004 — hermeticity_gate unit tests
# ---------------------------------------------------------------------------

def test_hermeticity_gate_pass_when_no_diff():
    """Identical before/after → PASS."""
    snap = {" M src/foo.py", "?? tests/tmp.txt"}
    result = gates.hermeticity_gate(snap, snap.copy(), "wave")
    assert result["gate"] == "HERMETICITY"
    assert result["status"] == "PASS"


def test_hermeticity_gate_fail_when_file_added():
    """New porcelain entry after pytest → FAIL and file named in offending."""
    before = {" M src/foo.py"}
    after = {" M src/foo.py", " M src/bar.py"}
    result = gates.hermeticity_gate(before, after, "task")
    assert result["status"] == "FAIL"
    assert result["gate"] == "HERMETICITY"
    assert any("src/bar.py" in entry for entry in result["offending"])


def test_hermeticity_gate_fail_names_all_offending():
    """All mutated paths appear in the offending list."""
    before: set = set()
    after = {" M src/alpha.py", " M src/beta.py"}
    result = gates.hermeticity_gate(before, after, "wave")
    assert result["status"] == "FAIL"
    assert len(result["offending"]) == 2


def test_hermeticity_gate_fail_when_file_removed():
    """Porcelain entry disappearing (e.g. staged/restored) counts as a mutation."""
    before = {" M src/foo.py", " M src/bar.py"}
    after = {" M src/foo.py"}
    result = gates.hermeticity_gate(before, after, "task")
    assert result["status"] == "FAIL"
    assert any("src/bar.py" in e for e in result["offending"])


def test_hermeticity_gate_empty_snapshots_pass():
    """Both snapshots empty (clean tree both sides) → PASS."""
    result = gates.hermeticity_gate(set(), set(), "wave")
    assert result["status"] == "PASS"


def test_hermeticity_gate_allowlist_exempts_entry(monkeypatch):
    """An entry in HERMETICITY_ALLOWLIST is not counted as an offending mutation."""
    exempt_line = " M scripts/generated_output.py"
    monkeypatch.setattr(gates, "HERMETICITY_ALLOWLIST",
                        frozenset([exempt_line]))
    before: set = set()
    after = {exempt_line}
    result = gates.hermeticity_gate(before, after, "wave")
    assert result["status"] == "PASS"


def test_hermeticity_gate_non_allowlisted_still_fails(monkeypatch):
    """Allowlist only covers the listed entry; other mutations still FAIL."""
    exempt_line = " M scripts/generated_output.py"
    monkeypatch.setattr(gates, "HERMETICITY_ALLOWLIST",
                        frozenset([exempt_line]))
    before: set = set()
    after = {exempt_line, " M src/real_change.py"}
    result = gates.hermeticity_gate(before, after, "wave")
    assert result["status"] == "FAIL"
    assert any("src/real_change.py" in e for e in result["offending"])


def test_hermeticity_gate_fail_appends_ledger(monkeypatch, tmp_path):
    """On FAIL, hermeticity_gate appends an entry to the harness ledger."""
    import json

    fake_ledger = tmp_path / "phase_ledger.jsonl"
    monkeypatch.setattr(gates.harness_state, "LEDGER", fake_ledger)

    before: set = set()
    after = {" M src/tainted.py"}
    result = gates.hermeticity_gate(before, after, "task")
    assert result["status"] == "FAIL"
    assert fake_ledger.exists()
    lines = [json.loads(l) for l in fake_ledger.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert lines[0]["event"] == "hermeticity_fail"
    assert lines[0]["tier"] == "task"
    assert any("src/tainted.py" in p for p in lines[0]["offending"])


def test_hermeticity_gate_pass_does_not_write_ledger(monkeypatch, tmp_path):
    """On PASS, hermeticity_gate must not write to the ledger."""
    fake_ledger = tmp_path / "phase_ledger.jsonl"
    monkeypatch.setattr(gates.harness_state, "LEDGER", fake_ledger)
    snap = {" M src/foo.py"}
    gates.hermeticity_gate(snap, snap.copy(), "wave")
    assert not fake_ledger.exists()


# ---------------------------------------------------------------------------
# 12. P0-H-004 — HERMETICITY wired into _scoped_g1 (mutation detection)
# ---------------------------------------------------------------------------

def test_scoped_g1_hermeticity_red_on_mutation(monkeypatch):
    """Criterion 1: mutating a tracked file mid-gate turns HERMETICITY red + names the file.

    Strategy: mock _git_porcelain to return a different set the second time it's
    called (simulating a file appearing dirty after pytest writes to it), and mock
    run_pytest to succeed fast.  Verify the returned gate list contains a
    HERMETICITY FAIL entry that names the mutated file.
    """
    mutated_line = " M src/kernel/some_tracked_file.py"
    call_count = {"n": 0}

    def _fake_porcelain() -> set:
        call_count["n"] += 1
        # Before pytest: clean; after pytest: one file mutated.
        if call_count["n"] == 1:
            return set()
        return {mutated_line}

    monkeypatch.setattr(gates, "_git_porcelain", _fake_porcelain)
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    # Use a tiny synthetic file list; _scoped_g1 also needs select_tests to pick targets.
    # Patch select_tests so it returns exactly one synthetic test file.
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)

    results = gates._scoped_g1(["src/kernel/some_tracked_file.py"], tier="wave")

    assert isinstance(results, list) and len(results) == 2
    gate_names = {r["gate"] for r in results}
    assert "G1" in gate_names and "HERMETICITY" in gate_names

    herm = next(r for r in results if r["gate"] == "HERMETICITY")
    assert herm["status"] == "FAIL", f"Expected HERMETICITY FAIL, got: {herm}"
    assert any("src/kernel/some_tracked_file.py" in entry for entry in herm["offending"]), (
        f"Mutated file not named in offending: {herm['offending']}"
    )


def test_scoped_g1_hermeticity_pass_no_mutation(monkeypatch):
    """Criterion 2: three consecutive gate runs with no mutations all return HERMETICITY PASS."""
    # Porcelain returns the same set every call (no drift).
    stable_snap = {" M some/pre_existing_dirty.py"}
    monkeypatch.setattr(gates, "_git_porcelain", lambda: set(stable_snap))
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 2, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)

    # Run 3 consecutive times — all must be HERMETICITY PASS.
    for i in range(3):
        results = gates._scoped_g1(["src/sim/basketball_sim.py"], tier="wave")
        herm = next(r for r in results if r["gate"] == "HERMETICITY")
        assert herm["status"] == "PASS", (
            f"Run {i + 1}/3: expected HERMETICITY PASS, got FAIL. offending={herm.get('offending')}"
        )


def test_scoped_g1_returns_list_of_two_gate_dicts(monkeypatch):
    """_scoped_g1 always returns exactly [G1-dict, HERMETICITY-dict]."""
    monkeypatch.setattr(gates, "_git_porcelain", lambda: set())
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)

    results = gates._scoped_g1(["src/foo.py"], tier="task")
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["gate"] == "G1"
    assert results[1]["gate"] == "HERMETICITY"


def test_scoped_g1_skip_returns_two_skip_dicts(monkeypatch):
    """When G1 is skipped (select_tests unavailable), both dicts are SKIP."""
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", False)
    results = gates._scoped_g1(["src/foo.py"], tier="wave")
    assert isinstance(results, list) and len(results) == 2
    assert all(r["status"] == "SKIP" for r in results)
    assert results[0]["gate"] == "G1"
    assert results[1]["gate"] == "HERMETICITY"


# ---------------------------------------------------------------------------
# 13. P0-H-004 — HERMETICITY appears in run_tier gates list
# ---------------------------------------------------------------------------

def test_run_tier_task_includes_hermeticity_on_success(monkeypatch):
    """task tier: HERMETICITY gate appears in the gates list after a clean run."""
    monkeypatch.setattr(gates, "_git_porcelain", lambda: set())
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)

    result = gates.run_tier("task", task_files=["src/sim/basketball_sim.py"])
    gate_names = [g["gate"] for g in result["gates"]]
    assert "HERMETICITY" in gate_names


def test_run_tier_wave_includes_hermeticity_on_success(monkeypatch):
    """wave tier: HERMETICITY gate appears in the gates list after a clean run."""
    monkeypatch.setattr(gates, "_git_porcelain", lambda: set())
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)

    result = gates.run_tier("wave", task_files=["src/sim/basketball_sim.py"])
    gate_names = [g["gate"] for g in result["gates"]]
    assert "HERMETICITY" in gate_names


def test_run_tier_task_hermeticity_fail_makes_verdict_fail(monkeypatch):
    """task tier: a HERMETICITY FAIL propagates to overall FAIL verdict."""
    call_count = {"n": 0}

    def _dirty_after() -> set:
        call_count["n"] += 1
        return set() if call_count["n"] == 1 else {" M src/dirty.py"}

    monkeypatch.setattr(gates, "_git_porcelain", _dirty_after)
    monkeypatch.setattr(gates, "run_pytest", lambda targets=None, timeout=1800: {
        "ran": True, "timed_out": False, "passed": 1, "failed": 0,
        "skipped": 0, "errors": 0, "rc": 0, "elapsed_s": 0.01,
    })
    import types
    fake_st = types.SimpleNamespace(
        select=lambda files, repo_root=None: {
            "tests": ["tests/platform/test_harness_gates.py"],
            "sentinel": None,
            "reason": "synthetic",
            "rules_fired": [],
        }
    )
    monkeypatch.setattr(gates, "_select_tests", fake_st)
    monkeypatch.setattr(gates, "_SELECT_AVAILABLE", True)
    monkeypatch.setattr(gates, "_script_exists", lambda rel: False)

    result = gates.run_tier("task", task_files=["src/sim/basketball_sim.py"])
    assert result["verdict"] == "FAIL"
    herm = next(g for g in result["gates"] if g["gate"] == "HERMETICITY")
    assert herm["status"] == "FAIL"
    assert any("src/dirty.py" in e for e in herm["offending"])
