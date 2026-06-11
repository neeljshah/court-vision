"""rollback.py — Phase rollback utility (EXECUTION_HARNESS §7.5).

Every phase opens with ``git tag platform-phase<N>-pre``. Rollback =
``git reset --hard platform-phase<N>-pre`` + mark phase/tasks rolled_back
+ ledger event + human-gates entry.  Registry/vault are NEVER touched.
The next pick skips a rolled_back phase until a human re-opens it.

Usage (dry-run, default-safe):
    python scripts/platform_harness/rollback.py --phase 2 --why "bad merge"
Usage (live — explicit opt-in only):
    python scripts/platform_harness/rollback.py --phase 2 --why "bad merge" --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_state  # noqa: E402

try:
    import backlog  # to enumerate a phase's task ids
except Exception:
    backlog = None  # type: ignore[assignment]

_GATES_FILE = ROOT / ".planning" / "platform" / "human-gates.md"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def phase_tasks(phase: str) -> List[str]:
    """Return sorted task ids belonging to *phase* from BUILD_BACKLOG.md ([] on failure)."""
    if backlog is None:
        return []
    try:
        tasks, _ = backlog.parse()
    except Exception:
        return []
    return sorted(
        tid for tid, task in tasks.items() if task.get("phase") == phase
    )


def git_reset_cmd(phase: str) -> List[str]:
    """Return the ``git reset --hard`` command list for *phase* (construction only, no exec)."""
    return ["git", "reset", "--hard", f"platform-phase{phase}-pre"]


def mark_rolled_back(state: dict, phase: str, why: str) -> dict:
    """Pure state-mutation helper: mark *phase* and its tasks ``rolled_back`` in *state*.

    No git, no disk write, no ledger — safe for unit tests on a temp dict.
    Returns the mutated *state*.
    """
    ts = dt.datetime.now().isoformat(timespec="seconds")
    harness_state.set_phase(
        state, phase,
        status="rolled_back",
        blocked_on=None,
        rolled_back_why=why,
        rolled_back_at=ts,
    )
    for tid in phase_tasks(phase):
        harness_state.set_task(state, tid, status="rolled_back")
    return state


def rollback(phase: str, why: str = "", execute: bool = False) -> dict:
    """Roll program phase *phase* back to its pre-tag.

    ``execute=False`` (default) prints the plan and returns it — NOTHING is run.
    ``execute=True`` runs git reset, updates state, ledger, and human-gates.
    """
    cmd = git_reset_cmd(phase)
    tasks = phase_tasks(phase)

    if not execute:
        print("=== ROLLBACK DRY-RUN (no changes made) ===")
        print(f"  phase      : {phase}")
        print(f"  git command: {' '.join(cmd)}")
        print(f"  task count : {len(tasks)}")
        if tasks:
            print(
                f"  tasks      : {', '.join(tasks[:10])}"
                + ("  ..." if len(tasks) > 10 else "")
            )
        print(f"  why        : {why or '(none)'}")
        print("  Pass --execute to perform the rollback for real.")
        return {"action": "rollback", "phase": phase, "execute": False,
                "git_cmd": cmd, "tasks": tasks}

    # ------------------------------------------------------------------ live
    # 1. Git reset (subprocess with timeout + try/except — never called in tests)
    git_rc: int = -1
    git_err: str = ""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=str(ROOT),
        )
        git_rc = proc.returncode
        git_err = proc.stderr.strip()
    except subprocess.TimeoutExpired:
        git_err = "git reset timed out after 60 s"
    except Exception as exc:  # noqa: BLE001
        git_err = f"git reset failed: {exc}"

    # 2. State mutation + save
    state = harness_state.load()
    mark_rolled_back(state, phase, why)
    harness_state.save(state)

    # 3. Ledger
    harness_state.append_ledger(
        "phase_rolled_back", phase=phase, why=why,
        n_tasks=len(tasks), git_returncode=git_rc,
    )

    # 4. Human-gates entry (append)
    raised = dt.datetime.now().isoformat(timespec="seconds")
    gate_block = (
        f"\n---\n\n"
        f"## [G-ROLLBACK-{phase}] phase {phase} rolled back\n"
        f"- STATUS: open\n"
        f"- BLOCKING: no\n"
        f"- RAISED: {raised}\n"
        f"- WHY: {why or '(no reason given)'}\n"
        f"- CONTEXT: Phase {phase} rolled back to platform-phase{phase}-pre. "
        f"Re-open: set phase status to 'todo' in build_state.json and answer this gate.\n"
        f"- ANSWER:\n"
    )
    _GATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _GATES_FILE.open("a", encoding="utf-8") as fh:
        fh.write(gate_block)

    out: dict = {"action": "rollback", "phase": phase, "execute": True,
                 "git_cmd": cmd, "tasks": tasks, "git_returncode": git_rc}
    if git_err:
        out["git_stderr"] = git_err
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Roll a platform phase back to its pre-tag.\n"
            "Default: DRY-RUN (prints plan, executes nothing).\n"
            "Pass --execute for a real rollback."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--phase", required=True, help="Phase id (e.g. 2)")
    p.add_argument("--why", default="", help="Human-readable reason")
    p.add_argument("--execute", action="store_true", default=False,
                   help="Perform the rollback (default: dry-run)")
    return p


if __name__ == "__main__":
    _args = _build_parser().parse_args()
    _result = rollback(phase=_args.phase, why=_args.why, execute=_args.execute)
    print(json.dumps(_result, indent=2))
