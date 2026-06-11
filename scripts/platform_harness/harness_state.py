"""harness_state.py — state-machine owner for the autonomous platform-build harness.

Owns `.planning/platform/build_state.json` (v1 schema).
Provides: crash-safe atomic load/save, status transitions, ledger append, CLI.

Usage:
    python scripts/platform_harness/harness_state.py --init [--force]
    python scripts/platform_harness/harness_state.py --print
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root (nba-ai-system)
sys.path.insert(0, str(ROOT / "scripts" / "bot_guards"))
from _state import write_json_atomic, read_json_safe   # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
STATE_FILE = ROOT / ".planning" / "platform" / "build_state.json"
LEDGER = ROOT / ".planning" / "platform" / "phase_ledger.jsonl"

# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------
TASK_STATUSES = (
    "todo",
    "ready",
    "in_progress",
    "review",
    "blocked",
    "done",
    "rejected",
    "rolled_back",
)

PHASE_STATUSES = (
    "todo",
    "in_progress",
    "gating",
    "done",
    "blocked",
    "rolled_back",
)

_ALL_PHASES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "N", "M"]

_PHASE_TEMPLATE = {
    "status": "todo",
    "pre_tag": None,
    "post_tag": None,
    "not_before": None,
    "blocked_on": None,
    "stop_window": None,
    "gates": {"G1": None, "G2": None, "G3": None, "G4": None, "G5": None},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current local time as ISO-8601 string with seconds resolution."""
    return dt.datetime.now().isoformat(timespec="seconds")


def _phase_entry() -> dict:
    """Return a fresh copy of the phase template."""
    entry = dict(_PHASE_TEMPLATE)
    entry["gates"] = dict(_PHASE_TEMPLATE["gates"])
    return entry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def default_state() -> dict:
    """Return the v1 schema skeleton with all 12 phases seeded as todo."""
    phases = {pid: _phase_entry() for pid in _ALL_PHASES}
    return {
        "schema_version": 1,
        "program": "platform_v1",
        "created": _now(),
        "phase_cursor": {"P": "0", "N": "open"},
        "phases": phases,
        "tasks": {},
        "waves": {},
        "counters": {
            "tasks_done": 0,
            "tasks_rejected": 0,
            "waves": 0,
            "escalations": 0,
        },
        "stop": {"requested": False},
    }


def exists() -> bool:
    """Return True if the state file is present on disk."""
    return STATE_FILE.exists()


def load() -> dict:
    """Load state from disk; return a fresh default if missing or corrupt.

    Does NOT write to disk — the caller is responsible for saving if needed.
    """
    return read_json_safe(STATE_FILE, default_state())


def save(state: dict) -> None:
    """Crash-safe atomic save of *state* to STATE_FILE."""
    write_json_atomic(STATE_FILE, state)


def init(force: bool = False) -> dict:
    """Initialise (or re-initialise) build_state.json.

    If the file already exists and *force* is False, load and return it
    unchanged.  Otherwise write a fresh default and append an init event to
    the ledger.
    """
    if exists() and not force:
        return load()
    state = default_state()
    save(state)
    append_ledger("build_state_init")
    return state


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def task_status(state: dict, task_id: str) -> str:
    """Return the status of *task_id*, defaulting to ``'todo'`` if absent."""
    return state["tasks"].get(task_id, {}).get("status", "todo")


def new_task_record(status: str = "todo", **fields) -> dict:
    """Build a per-task record with sane defaults, then overlay *fields*."""
    record: dict = {
        "status": status,
        "wave": None,
        "branch": None,
        "commit": None,
        "attempts": 0,
        "gates": {},
        "blocked_reason": None,
        "last_error": None,
        "claimed_by": None,
        "ts": _now(),
    }
    record.update(fields)
    return record


def set_task(state: dict, task_id: str, **fields) -> dict:
    """Upsert a task record in *state*, merging *fields*.

    Creates the record via :func:`new_task_record` if absent, then merges
    *fields* and refreshes ``ts``.  Returns the mutated *state* (caller saves).
    """
    tasks = state.setdefault("tasks", {})
    if task_id not in tasks:
        tasks[task_id] = new_task_record()
    tasks[task_id].update(fields)
    tasks[task_id]["ts"] = _now()
    return state


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------

def phase_status(state: dict, phase: str) -> str:
    """Return the status of *phase*, defaulting to ``'todo'`` if absent."""
    return state.get("phases", {}).get(phase, {}).get("status", "todo")


def set_phase(state: dict, phase: str, **fields) -> dict:
    """Merge *fields* into the phase record for *phase* (creating if absent).

    Returns the mutated *state*.
    """
    phases = state.setdefault("phases", {})
    if phase not in phases:
        phases[phase] = _phase_entry()
    phases[phase].update(fields)
    return state


# ---------------------------------------------------------------------------
# Wave helpers
# ---------------------------------------------------------------------------

def record_wave(state: dict, wave_id: str, tasks: list, **fields) -> dict:
    """Register a new wave and set it to ``'open'`` status.

    Returns the mutated *state*.
    """
    wave: dict = {
        "tasks": list(tasks),
        "status": "open",
        "spawned_at": _now(),
        "closed_at": None,
        "budget_h": None,
    }
    wave.update(fields)
    state.setdefault("waves", {})[wave_id] = wave
    return state


# ---------------------------------------------------------------------------
# Counter helpers
# ---------------------------------------------------------------------------

def bump_counter(state: dict, name: str, n: int = 1) -> dict:
    """Increment ``state['counters'][name]`` by *n*.  Returns the mutated *state*."""
    state.setdefault("counters", {})[name] = (
        state["counters"].get(name, 0) + n
    )
    return state


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def append_ledger(event: str, **fields) -> None:
    """Append one JSON line to the append-only ledger.

    Creates the ledger file (and its parent directory) if missing.
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now(), "event": event}
    entry.update(fields)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summary(state: dict) -> str:
    """Return a compact human-readable summary of *state* (≤20 lines)."""
    lines: list[str] = []

    program = state.get("program", "?")
    schema = state.get("schema_version", "?")
    cursor = state.get("phase_cursor", {})
    lines.append(f"program={program}  schema_v={schema}  created={state.get('created','?')}")
    lines.append(f"phase_cursor  P={cursor.get('P','?')}  N={cursor.get('N','?')}")

    # Task status counts
    task_counts: Counter = Counter()
    for tid in state.get("tasks", {}):
        task_counts[task_status(state, tid)] += 1
    if task_counts:
        counts_str = "  ".join(f"{s}={task_counts[s]}" for s in TASK_STATUSES if task_counts[s])
        lines.append(f"tasks  {counts_str}")
    else:
        lines.append("tasks  (none yet)")

    # Phase statuses — show non-todo + cursor phase
    cursor_phase = cursor.get("P", "")
    non_default_phases = []
    for pid in _ALL_PHASES:
        ps = phase_status(state, pid)
        if ps != "todo" or pid == cursor_phase:
            non_default_phases.append(f"{pid}={ps}")
    if non_default_phases:
        lines.append(f"phases  {', '.join(non_default_phases)}")
    else:
        lines.append("phases  all todo")

    # Open waves
    waves = state.get("waves", {})
    open_waves = [wid for wid, w in waves.items() if w.get("status") == "open"]
    if open_waves:
        lines.append(f"open_waves  {', '.join(open_waves)}")
    else:
        lines.append(f"waves  {len(waves)} total  0 open")

    # Counters
    counters = state.get("counters", {})
    ctr_str = "  ".join(f"{k}={v}" for k, v in counters.items())
    lines.append(f"counters  {ctr_str}")

    # Stop flag
    stop_req = state.get("stop", {}).get("requested", False)
    lines.append(f"stop_requested={stop_req}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Manage the platform build state file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument(
        "--init",
        action="store_true",
        help="Initialise build_state.json (no-op if already exists unless --force).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="With --init: overwrite an existing build_state.json.",
    )
    p.add_argument(
        "--print",
        dest="print_summary",
        action="store_true",
        help="Print a compact summary of the current state.",
    )
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.init:
        init(force=args.force)
        print(f"build_state.json initialized at {STATE_FILE}")
    elif args.print_summary:
        print(summary(load()))
    else:
        # Default: print summary
        print(summary(load()))
