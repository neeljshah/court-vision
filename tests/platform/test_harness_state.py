"""test_harness_state.py — Acceptance tests for harness_state.py (state machine + atomic write).

Python 3.9 compatible. No network.
IMPORTANT: all tests that write to disk use monkeypatch to redirect STATE_FILE and LEDGER
to tmp_path. The REAL build_state.json is NEVER modified.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import harness_state  # noqa: E402


# ---------------------------------------------------------------------------
# 1. default_state() schema.
# ---------------------------------------------------------------------------

def test_default_state_schema_version():
    ds = harness_state.default_state()
    assert ds["schema_version"] == 1


def test_default_state_all_12_phases():
    ds = harness_state.default_state()
    expected = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "N", "M"}
    assert set(ds["phases"].keys()) == expected, (
        f"Expected 12 phases, got {set(ds['phases'].keys())}"
    )


def test_default_state_all_phases_todo():
    ds = harness_state.default_state()
    for pid, phase in ds["phases"].items():
        assert phase["status"] == "todo", f"Phase {pid} should default to 'todo'"


def test_default_state_empty_tasks_and_waves():
    ds = harness_state.default_state()
    assert ds["tasks"] == {}
    assert ds["waves"] == {}


def test_default_state_counters_present():
    ds = harness_state.default_state()
    counters = ds.get("counters", {})
    assert "waves" in counters
    assert "tasks_done" in counters or len(counters) > 0, "counters dict should have entries"


# ---------------------------------------------------------------------------
# 2. task_status defaults to "todo"; set_task round-trip.
# ---------------------------------------------------------------------------

def test_task_status_missing_defaults_todo():
    state = harness_state.default_state()
    assert harness_state.task_status(state, "NONEXISTENT") == "todo"


def test_set_task_status_done():
    state = harness_state.default_state()
    harness_state.set_task(state, "X", status="done")
    assert harness_state.task_status(state, "X") == "done"


def test_set_task_idempotent_update():
    state = harness_state.default_state()
    harness_state.set_task(state, "X", status="in_progress")
    harness_state.set_task(state, "X", status="done")
    assert harness_state.task_status(state, "X") == "done"


# ---------------------------------------------------------------------------
# 3. set_phase / phase_status round-trip; record_wave; bump_counter.
# ---------------------------------------------------------------------------

def test_set_phase_and_phase_status():
    state = harness_state.default_state()
    harness_state.set_phase(state, "3", status="in_progress")
    assert harness_state.phase_status(state, "3") == "in_progress"


def test_phase_status_missing_defaults_todo():
    state = {"phases": {}, "tasks": {}}
    assert harness_state.phase_status(state, "99") == "todo"


def test_record_wave_open_status():
    state = harness_state.default_state()
    harness_state.record_wave(state, "W001", ["P0-A-001", "N-CLV-001"])
    wave = state["waves"]["W001"]
    assert wave["status"] == "open"
    assert wave["spawned_at"] is not None
    assert wave["tasks"] == ["P0-A-001", "N-CLV-001"]


def test_bump_counter():
    state = harness_state.default_state()
    before = state["counters"].get("waves", 0)
    harness_state.bump_counter(state, "waves")
    assert state["counters"]["waves"] == before + 1


def test_bump_counter_by_n():
    state = harness_state.default_state()
    harness_state.bump_counter(state, "waves", n=5)
    assert state["counters"]["waves"] == 5


def test_bump_counter_creates_key():
    state = {"counters": {}}
    harness_state.bump_counter(state, "new_key", n=3)
    assert state["counters"]["new_key"] == 3


# ---------------------------------------------------------------------------
# 4. Atomic write integrity (crash-sim).
# ---------------------------------------------------------------------------

def test_atomic_save_and_load(monkeypatch, tmp_path):
    target = tmp_path / "bs.json"
    monkeypatch.setattr(harness_state, "STATE_FILE", target)
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    state = harness_state.default_state()
    harness_state.set_task(state, "P0-A-001", status="done")
    harness_state.save(state)

    assert target.exists(), "State file should exist after save"

    # Read back and compare
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["tasks"]["P0-A-001"]["status"] == "done"
    assert loaded["schema_version"] == 1


def test_atomic_save_no_leftover_tmp_files(monkeypatch, tmp_path):
    target = tmp_path / "bs.json"
    monkeypatch.setattr(harness_state, "STATE_FILE", target)
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    state = harness_state.default_state()
    harness_state.save(state)

    # The only json file in the dir should be the target (no .tmp leftovers)
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1, (
        f"Expected exactly 1 json file after atomic save, found: {json_files}"
    )
    assert json_files[0] == target

    # No .tmp files should remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leftover .tmp files found: {tmp_files}"


# ---------------------------------------------------------------------------
# 5. load() on missing file returns fresh default WITHOUT creating the file.
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_default_without_creating(monkeypatch, tmp_path):
    nonexistent = tmp_path / "no_such_file.json"
    monkeypatch.setattr(harness_state, "STATE_FILE", nonexistent)
    monkeypatch.setattr(harness_state, "LEDGER", tmp_path / "ledger.jsonl")

    result = harness_state.load()

    # File must NOT be created
    assert not nonexistent.exists(), "load() must not create the state file if missing"

    # Returned value must be a valid default state
    assert result["schema_version"] == 1
    assert "phases" in result
    assert "tasks" in result


# ---------------------------------------------------------------------------
# 6. append_ledger appends valid JSON lines with ts + event.
# ---------------------------------------------------------------------------

def test_append_ledger_two_lines(monkeypatch, tmp_path):
    ledger_path = tmp_path / "test_ledger.jsonl"
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", ledger_path)

    harness_state.append_ledger("event_one", detail="alpha")
    harness_state.append_ledger("event_two", detail="beta")

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, f"Expected 2 ledger lines, got {len(lines)}"

    for line in lines:
        entry = json.loads(line)  # must be valid JSON
        assert "ts" in entry, "Ledger entry must have 'ts'"
        assert "event" in entry, "Ledger entry must have 'event'"


def test_append_ledger_correct_events(monkeypatch, tmp_path):
    ledger_path = tmp_path / "test_ledger2.jsonl"
    monkeypatch.setattr(harness_state, "STATE_FILE", tmp_path / "bs.json")
    monkeypatch.setattr(harness_state, "LEDGER", ledger_path)

    harness_state.append_ledger("my_event", phase="3")

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "my_event"
    assert entry["phase"] == "3"
