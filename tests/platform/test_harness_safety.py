"""test_harness_safety.py — Discipline invariants (no registry write, no git, no flag flip).

Python 3.9 compatible. No network.
CRITICAL: Every test that touches stop_window or harness_state must redirect
STATE_FILE and LEDGER to tmp_path. The REAL data/registry/STOP must never be created.
"""
import sys
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import stop_window   # noqa: E402
import rollback      # noqa: E402
import harness_state  # noqa: E402

REAL_STOP = ROOT / "data" / "registry" / "STOP"


# ---------------------------------------------------------------------------
# Safety pre-check: REAL STOP must not exist before any tests run.
# ---------------------------------------------------------------------------

def test_real_stop_does_not_exist_before_tests():
    assert not REAL_STOP.exists(), (
        f"REAL STOP file exists before tests — must not be present: {REAL_STOP}"
    )


# ---------------------------------------------------------------------------
# 1. STOP safety: open/close in tmp, REAL STOP never created.
# ---------------------------------------------------------------------------

def test_stop_open_creates_tmp_stop_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    result = stop_window.open_window("3", execute=True)

    assert result["execute"] is True
    # STOP file must be in tmp_path, not real registry
    expected_sf = tmp_path / "STOP"
    assert expected_sf.exists(), f"STOP file should exist in tmp_path: {expected_sf}"
    # REAL STOP must never have been created
    assert not REAL_STOP.exists(), f"REAL STOP was created — safety violation: {REAL_STOP}"


def test_stop_close_removes_tmp_stop_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    # open first, then close
    stop_window.open_window("3", execute=True)
    expected_sf = tmp_path / "STOP"
    assert expected_sf.exists(), "STOP should exist after open"

    stop_window.close_window("3", execute=True)
    assert not expected_sf.exists(), "STOP should be removed after close"
    assert not REAL_STOP.exists(), f"REAL STOP was created — safety violation: {REAL_STOP}"


def test_real_stop_not_created_during_open(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    assert not REAL_STOP.exists()
    stop_window.open_window("3", execute=True)
    assert not REAL_STOP.exists(), "REAL STOP must not exist after open_window in test mode"


def test_real_stop_not_created_during_close(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    stop_window.open_window("3", execute=True)
    stop_window.close_window("3", execute=True)
    assert not REAL_STOP.exists(), "REAL STOP must not exist after close_window in test mode"


# ---------------------------------------------------------------------------
# 2. STOP dry-run: returns execute==False and creates NO file.
# ---------------------------------------------------------------------------

def test_stop_dry_run_execute_false(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))

    result = stop_window.open_window("3", execute=False)
    assert result["execute"] is False


def test_stop_dry_run_creates_no_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))

    stop_window.open_window("3", execute=False)
    sf = stop_window.stop_file()
    assert not sf.exists(), (
        f"Dry-run should NOT create the STOP file, but it exists: {sf}"
    )


def test_stop_dry_run_real_stop_still_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_STOP_DIR", str(tmp_path))

    stop_window.open_window("3", execute=False)
    assert not REAL_STOP.exists()


# ---------------------------------------------------------------------------
# 3. Rollback safety: dry-run never calls git.
# ---------------------------------------------------------------------------

def test_rollback_dry_run_returns_correct_fields():
    result = rollback.rollback("2", why="test-why", execute=False)
    assert result["execute"] is False
    assert result["git_cmd"] == ["git", "reset", "--hard", "platform-phase2-pre"]


def test_rollback_dry_run_no_git(monkeypatch):
    """Monkeypatch rollback.subprocess.run to raise if called — dry-run must not call it."""
    def _must_not_run(*args, **kwargs):
        raise AssertionError("git must not run in dry-run")

    monkeypatch.setattr(rollback.subprocess, "run", _must_not_run)
    # This must succeed without calling subprocess.run
    result = rollback.rollback("2", why="safety-check", execute=False)
    assert result["execute"] is False


def test_rollback_dry_run_git_cmd_structure():
    result = rollback.rollback("2", execute=False)
    cmd = result["git_cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == "git"
    assert cmd[1] == "reset"
    assert cmd[2] == "--hard"
    assert "platform-phase2-pre" in cmd[3]


# ---------------------------------------------------------------------------
# 4. mark_rolled_back: pure helper, no side effects.
# ---------------------------------------------------------------------------

def test_mark_rolled_back_sets_phase_status():
    state = {"phases": {}, "tasks": {}, "counters": {}}
    rollback.mark_rolled_back(state, "2", "test reason")
    assert state["phases"]["2"]["status"] == "rolled_back", (
        f"Phase 2 should be rolled_back, got {state['phases'].get('2', {}).get('status')}"
    )


def test_mark_rolled_back_no_disk_write():
    """mark_rolled_back is a pure helper — it must not call harness_state.save."""
    state = {"phases": {}, "tasks": {}, "counters": {}}
    # Call it — if it tries to write to disk the real build_state.json would get
    # corrupted. We verify by checking the real file is untouched (size unchanged).
    real_state_path = ROOT / ".planning" / "platform" / "build_state.json"
    if real_state_path.exists():
        size_before = real_state_path.stat().st_size
        rollback.mark_rolled_back(state, "2", "pure helper test")
        size_after = real_state_path.stat().st_size
        assert size_before == size_after, "mark_rolled_back should NOT write to disk"
    else:
        # File doesn't exist — still run the function to confirm no error/creation
        rollback.mark_rolled_back(state, "2", "pure helper test")
        assert not real_state_path.exists(), "mark_rolled_back should not create build_state.json"


def test_mark_rolled_back_with_tasks_in_state():
    state = {
        "phases": {},
        "tasks": {"X-P2-014": {"status": "in_progress"}},
        "counters": {},
    }
    rollback.mark_rolled_back(state, "2", "reason")
    # Phase should be marked
    assert state["phases"]["2"]["status"] == "rolled_back"


# ---------------------------------------------------------------------------
# 5. Final sanity: REAL STOP was never created by this test module.
# ---------------------------------------------------------------------------

def test_real_stop_does_not_exist_after_all_tests():
    """Final guard: none of the tests above may have created the real STOP file."""
    assert not REAL_STOP.exists(), (
        f"SAFETY VIOLATION: A test created the real STOP file at {REAL_STOP}. "
        "Delete it and fix the offending test to use CV_STOP_DIR/tmp_path."
    )
