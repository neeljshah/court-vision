"""lane_status.py -- did the lanes actually dispatch, and did they actually commit?

WHY THIS EXISTS. On 2026-09-03 four separate things failed SILENTLY in one
session, and each cost real time before anyone noticed:

  1. Two `codex-sport` dispatches printed `REFUSE: ... unmerged commits` to a
     stdout that was piped away, so the lane never started and the orchestrator
     believed it was running.
  2. Two lanes did complete, correct work, exited 0, and committed NOTHING.
     Contract A7 requires the memo be committed BEFORE reporting, and an EXIT:0
     is not evidence that it was.
  3. A worktree's `data/` junction was a stale real directory holding 1 table
     instead of main's 423, so a lane measured an empty store and reported an
     honest-looking NOT VALIDATED that was really a provisioning defect.
  4. The pod filled toward its quota with no alarm anywhere.

The common shape: an exit code of 0 says a PROCESS ended, not that WORK
happened. This prints the difference. Nothing here changes state; it only looks.

Run:  python -m scripts.platformkit.lane_status
      python -m scripts.platformkit.lane_status a2 a5 a7
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from pathlib import Path

TEMP = Path(r"C:\Users\neelj\AppData\Local\Temp")
MAIN = Path(r"C:\Users\neelj\nba-ai-system")
WORKTREE = r"C:\Users\neelj\nba-track-%s"


def _git(repo: str, *args: str) -> str:
    """One git read. A failure returns empty rather than raising: this is a probe."""
    try:
        done = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=60)
        return done.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def lane_logs() -> dict:
    """Newest cx_<gap>.log per gap, with its dispatch and exit counts."""
    out = {}
    for path in glob.glob(str(TEMP / "cx_*.log")):
        name = Path(path).stem[3:]
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out[name] = {
            "path": path,
            # Anchored, and the exit code digit is required. A lane memo that quotes
            # the string EXIT: mid-document (G181 did) otherwise counts as a second
            # exit and makes a running lane look finished -- exactly the false signal
            # this tool exists to remove.
            "dispatched": len(re.findall(r"(?m)^DISPATCHED ", text)),
            "exited": len(re.findall(r"(?m)^EXIT:\d", text)),
            "mtime": os.path.getmtime(path),
        }
    return out


def worktree_state(home: str) -> dict:
    """Whether a worktree is free, dirty, or holding unlanded commits."""
    repo = WORKTREE % home
    if not os.path.isdir(repo):
        return {"exists": False}
    dirty = _git(repo, "status", "--porcelain", "--", ".")
    cherry = [l for l in _git(repo, "cherry", "master").splitlines() if l.startswith("+")]
    # A junction that is a stale real directory reads as a near-empty store; the
    # main repo's count is the only honest comparison.
    def _count(path: str) -> int:
        try:
            return len(os.listdir(path))
        except OSError:
            return -1
    return {
        "exists": True,
        "dirty": len([l for l in dirty.splitlines() if l.strip()]),
        "unlanded": len(cherry),
        "tracking": _count(os.path.join(repo, "data", "tracking")),
        "head": _git(repo, "log", "--oneline", "-1")[:48],
    }


def main(homes: list) -> int:
    homes = homes or ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9"]
    main_tracking = len(os.listdir(MAIN / "data" / "tracking")) if (MAIN / "data" / "tracking").is_dir() else -1

    print("WORKTREES (main data/tracking has %d entries)" % main_tracking)
    problems = []
    for home in homes:
        state = worktree_state(home)
        if not state["exists"]:
            continue
        flags = []
        if state["unlanded"]:
            flags.append("UNLANDED=%d (codex-sport will REFUSE)" % state["unlanded"])
        if state["dirty"]:
            flags.append("DIRTY=%d (codex-sport will REFUSE)" % state["dirty"])
        # a store an order of magnitude short of main is a provisioning defect
        if 0 <= state["tracking"] < max(2, main_tracking // 10):
            flags.append("TRACKING=%d vs main %d -- STALE JUNCTION"
                         % (state["tracking"], main_tracking))
        mark = "  PROBLEM: " + "; ".join(flags) if flags else "  ok"
        if flags:
            problems.append(home)
        print("  %-4s %s" % (home, mark))

    print("\nLANES (exit 0 is NOT evidence of a commit)")
    for name, info in sorted(lane_logs().items(), key=lambda kv: -kv[1]["mtime"])[:12]:
        if info["dispatched"] == 0:
            state = "NEVER DISPATCHED"
        elif info["dispatched"] > info["exited"]:
            state = "running"
        else:
            state = "finished"
        print("  %-42s %-16s dispatched=%d exited=%d"
              % (name[:42], state, info["dispatched"], info["exited"]))

    if problems:
        print("\n%d worktree(s) need freeing before dispatch: %s"
              % (len(problems), " ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
