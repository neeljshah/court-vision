"""test_harness_backlog.py — Acceptance tests for backlog.py (parser + ready-set DAG).

Python 3.9 compatible. No network. Uses the REAL parse() task set (stable: 75 tasks).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import backlog  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def state_with_done(done_ids, waves=0):
    return {
        "tasks": {i: {"status": "done"} for i in done_ids},
        "phases": {},
        "phase_cursor": {"P": "0", "N": "open"},
        "counters": {"waves": waves},
    }


# ---------------------------------------------------------------------------
# 1. parse() returns the full task set with 0 hard errors.
#    The backlog GROWS as the autonomous loop decomposes phases (75 at H0,
#    +8 P0-H gate-hardening, more later), so assert a FLOOR + no parse errors
#    rather than a magic exact count that breaks the gate on every addition.
# ---------------------------------------------------------------------------

def test_parse_count_and_no_errors():
    tasks, errors = backlog.parse()
    assert len(tasks) >= 75, f"Expected >= 75 tasks (H0 baseline), got {len(tasks)}"
    assert errors == [], f"Expected 0 hard errors, got: {errors}"


def test_parse_no_template_ids():
    """The §1 TASK SCHEMA template block must NOT appear as a task."""
    tasks, _ = backlog.parse()
    id_re = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
    for tid in tasks:
        assert "#" not in tid, f"Template-like id leaked in: {tid!r}"
        assert "<" not in tid, f"Template-like id leaked in: {tid!r}"
        assert id_re.match(tid), f"Id does not match expected pattern: {tid!r}"


# ---------------------------------------------------------------------------
# 2. Round-trip stability: parse() twice → identical id sets.
# ---------------------------------------------------------------------------

def test_parse_round_trip_stability():
    tasks1, _ = backlog.parse()
    tasks2, _ = backlog.parse()
    assert set(tasks1.keys()) == set(tasks2.keys())


# ---------------------------------------------------------------------------
# 3. Known tasks present with expected fields.
# ---------------------------------------------------------------------------

def test_known_task_p0_a_001():
    tasks, _ = backlog.parse()
    t = tasks.get("P0-A-001")
    assert t is not None, "P0-A-001 not found"
    assert t["depends_on"] == [], f"P0-A-001 should have no deps, got {t['depends_on']}"
    assert t["phase"] == "0", f"P0-A-001 should be phase 0, got {t['phase']}"


def test_known_task_p0_f_005():
    tasks, _ = backlog.parse()
    t = tasks.get("P0-F-005")
    assert t is not None, "P0-F-005 not found"
    assert t["depends_on"] == [], f"P0-F-005 should have no deps, got {t['depends_on']}"
    assert t["phase"] == "0", f"P0-F-005 should be phase 0, got {t['phase']}"


def test_known_task_n_clv_001():
    tasks, _ = backlog.parse()
    t = tasks.get("N-CLV-001")
    assert t is not None, "N-CLV-001 not found"
    assert t["phase"] == "N", f"N-CLV-001 should be phase N, got {t['phase']}"


def test_known_task_x_p2_gate():
    tasks, _ = backlog.parse()
    t = tasks.get("X-P2-GATE")
    assert t is not None, "X-P2-GATE not found"
    # Phase is derived from epic X-P2 → phase "2"
    assert t["phase"] == "2", f"X-P2-GATE should derive phase 2, got {t['phase']}"


# ---------------------------------------------------------------------------
# 4. ready_set with empty state.
# ---------------------------------------------------------------------------

def test_ready_set_empty_state_includes_expected():
    tasks, _ = backlog.parse()
    state = state_with_done([])
    ready = backlog.ready_set(state, tasks)
    ready_ids = {t["id"] for t in ready}

    assert "P0-A-001" in ready_ids, "P0-A-001 should be ready with empty state"
    assert "P0-F-005" in ready_ids, "P0-F-005 should be ready with empty state"
    assert "N-CLV-001" in ready_ids, "N-CLV-001 should be ready with empty state"


def test_ready_set_empty_state_excludes_expected():
    tasks, _ = backlog.parse()
    state = state_with_done([])
    ready = backlog.ready_set(state, tasks)
    ready_ids = {t["id"] for t in ready}

    # P0-A-002 depends on P0-A-001 (not done)
    assert "P0-A-002" not in ready_ids, "P0-A-002 should not be ready (dep not done)"
    # X-P2-GATE is phase 2, active phase is 0
    assert "X-P2-GATE" not in ready_ids, "X-P2-GATE should not be ready (wrong phase)"
    # Phase-1 T- tasks should not be eligible during phase 0
    t_in_ready = [tid for tid in ready_ids if tid.startswith("T-")]
    assert t_in_ready == [], f"Phase-1 T- tasks should not be ready during phase 0: {t_in_ready}"


# ---------------------------------------------------------------------------
# 5. DAG transition: P0-A-001 done → P0-A-002 becomes ready, P0-A-001 not ready.
# ---------------------------------------------------------------------------

def test_dag_transition_p0_a_001_done():
    tasks, _ = backlog.parse()
    state = state_with_done(["P0-A-001"])
    ready = backlog.ready_set(state, tasks)
    ready_ids = {t["id"] for t in ready}

    assert "P0-A-002" in ready_ids, "P0-A-002 should be ready once P0-A-001 is done"
    assert "P0-A-001" not in ready_ids, "P0-A-001 should not be ready (it is done)"


# ---------------------------------------------------------------------------
# 6. Track-N always eligible: ready set always contains at least one N- task.
# ---------------------------------------------------------------------------

def test_track_n_always_eligible_empty_state():
    tasks, _ = backlog.parse()
    state = state_with_done([])
    ready = backlog.ready_set(state, tasks)
    n_ready = [t for t in ready if t["id"].startswith("N-")]
    assert len(n_ready) >= 1, f"Expected at least one N- task in ready set (empty state), got: {[t['id'] for t in ready]}"


def test_track_n_always_eligible_all_phase0_done():
    tasks, _ = backlog.parse()
    phase0_ids = [tid for tid, t in tasks.items() if t.get("phase") == "0"]
    state = state_with_done(phase0_ids)
    ready = backlog.ready_set(state, tasks)
    n_ready = [t for t in ready if t["id"].startswith("N-")]
    assert len(n_ready) >= 1, (
        f"Expected at least one N- task ready after all phase-0 done, got: {[t['id'] for t in ready]}"
    )


# ---------------------------------------------------------------------------
# 7. deps_satisfied: range dep and epic dep logic.
# ---------------------------------------------------------------------------

def test_deps_satisfied_range_dep_unsatisfied():
    tasks, _ = backlog.parse()
    state = state_with_done([])
    # X-P2-GATE has range dep "X-P2-014..017" → not satisfied with empty state
    t = tasks["X-P2-GATE"]
    assert not backlog.deps_satisfied(t, state, tasks), (
        "X-P2-GATE range dep should not be satisfied with empty state"
    )


def test_deps_satisfied_epic_satisfied():
    tasks, _ = backlog.parse()
    # N-CLV epic members
    n_clv_members = [tid for tid, t in tasks.items() if backlog.epic_of(t) == "N-CLV"]
    assert len(n_clv_members) > 0, "Expected N-CLV epic to have members"

    state_all_done = state_with_done(n_clv_members)
    assert backlog.epic_done(state_all_done, "N-CLV", tasks), (
        "N-CLV epic should be done when all members are done"
    )
    state_empty = state_with_done([])
    assert not backlog.epic_done(state_empty, "N-CLV", tasks), (
        "N-CLV epic should not be done with empty state"
    )


def test_deps_satisfied_single_dep_not_met():
    tasks, _ = backlog.parse()
    state = state_with_done([])
    # P0-A-002 depends on P0-A-001 (not done)
    t = tasks["P0-A-002"]
    assert not backlog.deps_satisfied(t, state, tasks)


def test_deps_satisfied_single_dep_met():
    tasks, _ = backlog.parse()
    state = state_with_done(["P0-A-001"])
    t = tasks["P0-A-002"]
    assert backlog.deps_satisfied(t, state, tasks)


# ---------------------------------------------------------------------------
# 8. Validation: no absolute paths in files (enforced by 0 hard errors).
# ---------------------------------------------------------------------------

def test_no_absolute_paths_in_files():
    """parse() returning 0 errors means no absolute paths in files fields."""
    tasks, errors = backlog.parse()
    # Confirm 0 errors: absence of absolute-path errors
    abs_path_errors = [e for e in errors if "absolute path" in e]
    assert abs_path_errors == [], f"Found absolute path errors: {abs_path_errors}"

    # Additional direct check on all file entries
    for tid, task in tasks.items():
        for fp in task.get("files", []):
            norm = fp.replace("\\", "/")
            assert not re.match(r"^[A-Za-z]:/", norm), f"{tid}: absolute path {fp!r}"
            assert not norm.startswith("/"), f"{tid}: absolute path {fp!r}"
            parts = norm.split("/")
            assert ".." not in parts, f"{tid}: '..' in files path {fp!r}"
