"""build_status.py — cheap step-1 probe for the autonomous platform build orchestrator.

Prints the full resume picture in ≤20 grep-able lines on any machine, any session, cold.
Tells the bot "what is left" instantly without touching any file on disk.

Usage:
    python scripts/platform_harness/build_status.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_state  # noqa: E402
import backlog         # noqa: E402

_HUMAN_GATES_DEFAULT = ROOT / ".planning" / "platform" / "human-gates.md"
_LIVE_STATUS_PATH = ROOT / ".bot_state" / "live_status.json"


# ---------------------------------------------------------------------------
# human_gate_counts
# ---------------------------------------------------------------------------

def human_gate_counts(path: Path = _HUMAN_GATES_DEFAULT) -> dict:
    """Parse human-gates.md and return counts of open/answered gate items.

    Each gate block starts with a line matching ``^##\\s+\\[``. Within each block,
    ``- STATUS:`` and ``- BLOCKING:`` values are extracted case-insensitively.

    Returns:
        dict with keys ``open_blocking`` (open AND blocking==yes),
        ``open_total`` (all open), ``answered`` (STATUS==answered).
        All zeros when the file is absent.
    """
    if not path.exists():
        return {"open_blocking": 0, "open_total": 0, "answered": 0}

    text = path.read_text(encoding="utf-8")
    # Split into blocks; each starts at a "## [" heading
    raw_blocks = re.split(r"(?m)^##\s+\[", text)
    # First element before the first heading is the file preamble — drop it
    blocks = raw_blocks[1:]

    open_blocking = 0
    open_total = 0
    answered = 0

    _status_re = re.compile(r"(?im)^-?\s*STATUS:\s*(\w+)")
    _blocking_re = re.compile(r"(?im)^-?\s*BLOCKING:\s*(\w+)")

    for block in blocks:
        sm = _status_re.search(block)
        bm = _blocking_re.search(block)
        status = sm.group(1).lower() if sm else "unknown"
        blocking = bm.group(1).lower() if bm else "no"

        if status == "open":
            open_total += 1
            if blocking == "yes":
                open_blocking += 1
        elif status == "answered":
            answered += 1

    return {"open_blocking": open_blocking, "open_total": open_total, "answered": answered}


# ---------------------------------------------------------------------------
# gather
# ---------------------------------------------------------------------------

def gather(state: dict | None = None) -> dict:
    """Compute the full resume picture and return it as a plain dict.

    Parameters:
        state: pre-loaded harness state dict. If None, loaded from disk.

    Returns:
        dict with all fields needed by :func:`render` (and usable by tests).
    """
    if state is None:
        state = harness_state.load()

    # ── program + phase_cursor ─────────────────────────────────────────────
    program = state.get("program", "platform_v1")
    phase_cursor = state.get("phase_cursor", {}).get("P", "0")

    # ── tasks from backlog ─────────────────────────────────────────────────
    tasks, _errors = backlog.parse()
    total = len(tasks)

    counts = {"done": 0, "in_progress": 0, "review": 0, "blocked": 0, "rejected": 0,
              "todo": 0, "ready": 0, "rolled_back": 0}
    for tid in tasks:
        st = harness_state.task_status(state, tid)
        if st in counts:
            counts[st] += 1
        else:
            counts["todo"] += 1  # unknown → todo

    todo_or_ready = counts["todo"] + counts["ready"]
    percent_done = round(counts["done"] / total * 100, 1) if total else 0.0

    # ── active phase + ready set ───────────────────────────────────────────
    active = backlog.active_phase(state, tasks)
    ready_tasks = backlog.ready_set(state, tasks)
    ready_count = len(ready_tasks)
    next3 = [t["id"] for t in ready_tasks[:3]]

    # ── in-flight wave ─────────────────────────────────────────────────────
    waves = state.get("waves", {})
    in_flight = "none"
    for wid, wave in waves.items():
        if wave.get("status") == "open":
            in_flight = wid
            break

    # ── stop_requested ────────────────────────────────────────────────────
    stop_requested = False
    if _LIVE_STATUS_PATH.exists():
        try:
            ls = json.loads(_LIVE_STATUS_PATH.read_text(encoding="utf-8"))
            stop_requested = bool(ls.get("stop_requested", False))
        except (json.JSONDecodeError, OSError):
            stop_requested = state.get("stop", {}).get("requested", False)
    else:
        stop_requested = state.get("stop", {}).get("requested", False)

    # ── human gates ────────────────────────────────────────────────────────
    gates = human_gate_counts()

    return {
        "program": program,
        "phase_cursor": phase_cursor,
        "total": total,
        "done": counts["done"],
        "in_progress": counts["in_progress"],
        "review": counts["review"],
        "blocked": counts["blocked"],
        "rejected": counts["rejected"],
        "todo_or_ready": todo_or_ready,
        "percent_done": percent_done,
        "active_phase": active,
        "ready": ready_count,
        "next3": next3,
        "in_flight_wave": in_flight,
        "stop_requested": stop_requested,
        "open_blocking": gates["open_blocking"],
        "open_total": gates["open_total"],
        "answered": gates["answered"],
    }


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(info: dict) -> str:
    """Format the resume picture as a ≤20-line grep-able string.

    Parameters:
        info: dict as returned by :func:`gather`.

    Returns:
        Multi-line string suitable for printing to stdout.
    """
    next3_str = ", ".join(info["next3"]) if info["next3"] else "none"
    lines = [
        f"program={info['program']}  phase_cursor={info['phase_cursor']}",
        (
            f"tasks  total={info['total']}  done={info['done']}"
            f"  in_progress={info['in_progress']}  review={info['review']}"
            f"  blocked={info['blocked']}  rejected={info['rejected']}"
            f"  todo/ready={info['todo_or_ready']}"
        ),
        f"percent_done={info['percent_done']}%",
        f"active_phase={info['active_phase']}",
        f"ready={info['ready']}   (next3: {next3_str})",
        f"blocked={info['blocked']}",
        (
            f"human_gates  open_blocking={info['open_blocking']}"
            f"  open_total={info['open_total']}   answered={info['answered']}"
        ),
        f"in_flight_wave={info['in_flight_wave']}",
        f"stop_requested={info['stop_requested']}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(render(gather()))
    sys.exit(0)
