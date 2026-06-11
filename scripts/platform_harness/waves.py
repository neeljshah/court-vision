"""waves.py — Dependency-aware WAVE PLANNER with file-collision detection.

Given the ready set (from backlog.ready_set), returns the next maximal batch
of tasks whose ``files`` lists are PAIRWISE DISJOINT, respecting serial
constraints, per-class wave caps, and an optional game-day filter.

Collisions are caught mechanically here, never at merge time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog        # noqa: E402
import harness_state  # noqa: E402

# ---------------------------------------------------------------------------
# HOT / implicit-shared files — any task listing one triggers SERIAL execution
# ---------------------------------------------------------------------------

HOT_FILES: Set[str] = {
    "src/brain/flags.py",
    "conftest.py",
    "api/main.py",
    "requirements.txt",
    "environment.yml",
    "database/schema.sql",
    "CLAUDE.md",
    ".gitignore",
    "src/prediction/betting_portfolio.py",
}

_GLOB_CHARS = set("*?[")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def expand_files(task: dict, root: Path = ROOT) -> Set[str]:
    """Return repo-relative posix paths for all files in the task.

    Glob patterns (containing ``*``, ``?``, or ``[``) are expanded via the
    filesystem; literal paths are returned as-is.
    """
    result: Set[str] = set()
    for path_str in task.get("files", []):
        if any(c in path_str for c in _GLOB_CHARS):
            for match in root.glob(path_str):
                try:
                    result.add(match.relative_to(root).as_posix())
                except ValueError:
                    pass
        else:
            result.add(path_str)
    return result


def is_serial(task: dict) -> bool:
    """Return True if the task must run alone (serial wave).

    Triggered by: size == "L", owner_model == "opus",
    any file in HOT_FILES, or change_kind == "ops".
    """
    if task.get("size") == "L":
        return True
    if task.get("owner_model") == "opus":
        return True
    if task.get("change_kind") == "ops":
        return True
    for f in task.get("files", []):
        if f in HOT_FILES:
            return True
    return False


def cap_for(task: dict) -> int:
    """Wave-size cap: move→6, serial→1, else→8."""
    if is_serial(task):
        return 1
    if task.get("change_kind") == "move":
        return 6
    return 8


def game_day_eligible(task: dict) -> bool:
    """Return True if safe to land on an NBA game day (EXECUTION_HARNESS §6.6).

    Conservative: excludes move, serial, and anything touching src/api/loop.
    """
    ck = task.get("change_kind", "")
    phase = task.get("phase", "")
    files = task.get("files", [])

    if ck == "move":
        return False
    if is_serial(task):
        return False
    for f in files:
        if f.startswith("src/") or f.startswith("api/") or "loop" in f:
            return False

    if ck in {"doc", "test", "verify"}:
        return True
    if ck == "new":
        if files and all(
            f.startswith("kernel/") or f.startswith("tests/") for f in files
        ):
            return True
        return False
    if phase == "N" and ck in {"doc", "test", "new", "verify"}:
        return True
    return False


def pairwise_disjoint(file_sets: List[Set[str]]) -> bool:
    """Return True iff no two sets in *file_sets* share any element."""
    seen: Set[str] = set()
    for fs in file_sets:
        if fs & seen:
            return False
        seen |= fs
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _next_wave_id(state: dict) -> str:
    """Derive next wave id from state counter (deterministic, resume-safe)."""
    n = state.get("counters", {}).get("waves", 0) + 1
    return "W%03d" % n


def _wave_result(wave_tasks: List[dict], state: dict) -> dict:
    """Build the wave result dict."""
    claimed: Set[str] = set()
    for t in wave_tasks:
        claimed |= expand_files(t)
    serial_flag = (
        len(wave_tasks) == 1 and bool(wave_tasks) and is_serial(wave_tasks[0])
    )
    return {
        "wave_id": _next_wave_id(state),
        "tasks": [t["id"] for t in wave_tasks],
        "files": sorted(claimed),
        "size": len(wave_tasks),
        "serial": serial_flag,
    }


# ---------------------------------------------------------------------------
# Core planner
# ---------------------------------------------------------------------------

def plan_wave(
    state: Optional[Dict] = None,
    tasks: Optional[Dict] = None,
    game_day: bool = False,
    locked_files: Optional[Set[str]] = None,
) -> dict:
    """Plan the next maximal wave of tasks with pairwise-disjoint file sets.

    Args:
        state: Harness state dict (loaded from disk if None).
        tasks: Task dict keyed by id (parsed from backlog if None).
        game_day: When True, restrict to game-day-eligible tasks.
        locked_files: Additional files already claimed by a running wave.

    Returns:
        Wave result dict: wave_id, tasks, files, size, serial.

    Algorithm:
      1. Compute ready set (critical-path sorted).
      2. Optionally filter to game-day-eligible tasks.
      3. Greedy disjoint batch:
         - First serial task seen → solo wave returned immediately.
         - Serial task mid-scan → deferred (skip).
         - Non-serial tasks added while file sets stay disjoint.
         - Wave closes when per-class cap reached.
      4. Hard pairwise-disjoint assertion before return.
    """
    if state is None:
        state = harness_state.load()
    if tasks is None:
        tasks, _ = backlog.parse()

    ready: List[dict] = backlog.ready_set(state, tasks)
    if game_day:
        ready = [t for t in ready if game_day_eligible(t)]

    wave: List[dict] = []
    claimed: Set[str] = set(locked_files or [])

    for t in ready:
        fset = expand_files(t)
        if is_serial(t):
            if not wave:
                return _wave_result([t], state)
            else:
                continue
        if fset & claimed:
            continue
        wave.append(t)
        claimed |= fset
        if len(wave) >= cap_for(t):
            break

    # Hard disjointness check — defense in depth
    all_fsets = [expand_files(t) for t in wave]
    assert pairwise_disjoint(all_fsets), (
        f"Wave file sets are NOT pairwise disjoint: {all_fsets}"
    )

    return _wave_result(wave, state)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    p = argparse.ArgumentParser(
        description="Dependency-aware wave planner with file-collision detection."
    )
    p.add_argument("--plan", action="store_true", default=True,
                   help="Plan the next wave from disk state (default).")
    p.add_argument("--game-day", action="store_true", default=False,
                   help="Restrict to game-day-eligible tasks.")
    p.add_argument("--json", dest="as_json", action="store_true", default=False,
                   help="Print the wave dict as JSON.")
    args = p.parse_args()

    wave = plan_wave(game_day=args.game_day)

    if args.as_json:
        print(json.dumps(wave, indent=2))
        return

    print(f"wave_id  : {wave['wave_id']}")
    print(f"size     : {wave['size']}")
    print(f"serial   : {wave['serial']}")
    print("tasks    :")
    for tid in wave["tasks"]:
        print(f"  {tid}")
    print(f"files claimed: {len(wave['files'])}")


if __name__ == "__main__":
    _main()
