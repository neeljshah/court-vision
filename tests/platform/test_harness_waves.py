"""test_harness_waves.py — Acceptance tests for waves.py (collision avoidance).

Python 3.9 compatible. No network.
The core safety property: every planned wave has pairwise-disjoint file sets.
"""
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import backlog  # noqa: E402
import waves    # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def state_with_done(done_ids, wave_count=0):
    return {
        "tasks": {i: {"status": "done"} for i in done_ids},
        "phases": {},
        "phase_cursor": {"P": "0", "N": "open"},
        "counters": {"waves": wave_count},
    }


# Pre-parse tasks once for the module (stable 75-task set)
_TASKS, _ = backlog.parse()
_PHASE0_IDS = [tid for tid, t in _TASKS.items() if t.get("phase") == "0"]


# ---------------------------------------------------------------------------
# 1. Disjointness PROPERTY: planned wave's expand_files sets are pairwise disjoint.
# ---------------------------------------------------------------------------

def _assert_wave_disjoint(state):
    wave = waves.plan_wave(state, _TASKS)
    fsets = [waves.expand_files(_TASKS[tid]) for tid in wave["tasks"] if tid in _TASKS]
    assert waves.pairwise_disjoint(fsets), (
        f"Wave file sets NOT pairwise disjoint for wave {wave['tasks']}: {fsets}"
    )


def test_disjointness_empty_state():
    _assert_wave_disjoint(state_with_done([]))


def test_disjointness_p0_a_001_done():
    _assert_wave_disjoint(state_with_done(["P0-A-001"]))


def test_disjointness_several_done():
    done = ["P0-A-001", "P0-A-002", "P0-A-003"]
    _assert_wave_disjoint(state_with_done(done))


def test_disjointness_many_done():
    # Mark half of phase-0 done to stress more of the DAG
    done = _PHASE0_IDS[:len(_PHASE0_IDS) // 2]
    _assert_wave_disjoint(state_with_done(done))


def test_pairwise_disjoint_helper_true():
    sets = [{"a", "b"}, {"c", "d"}, {"e"}]
    assert waves.pairwise_disjoint(sets)


def test_pairwise_disjoint_helper_false():
    sets = [{"a", "b"}, {"b", "c"}]
    assert not waves.pairwise_disjoint(sets)


def test_pairwise_disjoint_empty():
    assert waves.pairwise_disjoint([])
    assert waves.pairwise_disjoint([set()])


# ---------------------------------------------------------------------------
# 2. Serial-solo: P0-A-001 touches .gitignore (HOT) → wave is exactly [P0-A-001].
# ---------------------------------------------------------------------------

def test_serial_solo_p0_a_001():
    state = state_with_done([])
    wave = waves.plan_wave(state, _TASKS)
    assert wave["tasks"] == ["P0-A-001"], (
        f"Expected solo wave [P0-A-001] (serial HOT file), got {wave['tasks']}"
    )
    assert wave["size"] == 1
    assert wave["serial"] is True


# ---------------------------------------------------------------------------
# 3. is_serial: size L → serial; HOT file → serial; plain S/new/kernel → not serial.
# ---------------------------------------------------------------------------

def test_is_serial_size_l():
    task = {"size": "L", "files": ["kernel/x.py"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.is_serial(task)


def test_is_serial_hot_file():
    task = {"size": "S", "files": [".gitignore"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.is_serial(task)


def test_is_serial_another_hot_file():
    task = {"size": "S", "files": ["CLAUDE.md"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.is_serial(task)


def test_is_serial_plain_not_serial():
    task = {"size": "S", "files": ["kernel/x.py"], "change_kind": "new", "owner_model": "sonnet"}
    assert not waves.is_serial(task)


def test_is_serial_opus_owner():
    task = {"size": "S", "files": ["kernel/x.py"], "change_kind": "new", "owner_model": "opus"}
    assert waves.is_serial(task)


def test_is_serial_ops_change_kind():
    task = {"size": "S", "files": ["kernel/x.py"], "change_kind": "ops", "owner_model": "sonnet"}
    assert waves.is_serial(task)


# ---------------------------------------------------------------------------
# 4. Game-day filter: no serial, no move; still non-empty.
# ---------------------------------------------------------------------------

def test_game_day_no_serial_tasks():
    state = state_with_done([])
    wave = waves.plan_wave(state, _TASKS, game_day=True)
    for tid in wave["tasks"]:
        t = _TASKS.get(tid, {})
        assert not waves.is_serial(t), (
            f"Serial task {tid} must not appear in game-day wave"
        )


def test_game_day_no_move_tasks():
    state = state_with_done([])
    wave = waves.plan_wave(state, _TASKS, game_day=True)
    for tid in wave["tasks"]:
        t = _TASKS.get(tid, {})
        assert t.get("change_kind") != "move", (
            f"Move task {tid} must not appear in game-day wave"
        )


def test_game_day_non_empty():
    state = state_with_done([])
    wave = waves.plan_wave(state, _TASKS, game_day=True)
    assert wave["size"] >= 1, "Game-day wave should be non-empty (docs/tests/new-kernel eligible)"


# ---------------------------------------------------------------------------
# 5. cap_for: move→6, serial→1, else→8.
# ---------------------------------------------------------------------------

def test_cap_for_move():
    task = {"size": "S", "files": ["kernel/x.py"], "change_kind": "move", "owner_model": "sonnet"}
    assert waves.cap_for(task) == 6


def test_cap_for_serial():
    task = {"size": "L", "files": ["kernel/x.py"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.cap_for(task) == 1


def test_cap_for_hot_file_serial():
    task = {"size": "S", "files": [".gitignore"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.cap_for(task) == 1


def test_cap_for_plain():
    task = {"size": "S", "files": ["kernel/x.py"], "change_kind": "new", "owner_model": "sonnet"}
    assert waves.cap_for(task) == 8
