"""Scheduled-task entry point for the footage-bridge keeper, with no console.

WHY THIS EXISTS instead of bridge_watchdog.cmd.

The scheduled task used to run ``cmd.exe /c bridge_watchdog.cmd``. A scheduled
CONSOLE command opens a visible window every time it fires, and this task fires
every five minutes, so it put a terminal window on the user's desktop all day.
Setting ``<Hidden>true</Hidden>`` on the task does NOT fix it -- that flag only
hides the task in the Task Scheduler UI. Nor do the child ``creationflags``: the
window belongs to the cmd.exe the scheduler itself starts, above any child.

The two real fixes are an S4U / "run whether user is logged on or not" logon, or
an action that is not a console program. This is the second, and the cheaper one:
``pythonw.exe`` has no console at all, so nothing can be shown.

stdout and stderr are redirected here rather than by shell ``>>`` because
pythonw has no shell and no inherited handles; without this the keeper's status
lines would be discarded and a wedged bridge would be undiagnosable.

Task action:
    Program:   <python dir>\\pythonw.exe
    Arguments: -m scripts.platformkit.bridge_watchdog_launch
    Start in:  C:\\Users\\neelj\\nba-ai-system
"""
from __future__ import annotations

import datetime
import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "logs" / "bridge_watchdog.log"


def main() -> int:
    os.chdir(REPO)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    # Append, never truncate: this file is the only record that the task ran at
    # all, and a truncating open would erase the previous tick's evidence.
    handle = LOG.open("a", encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr = handle
    print("--- watchdog tick %s ---" % datetime.datetime.now().isoformat(timespec="seconds"))
    sys.argv = ["bridge_keeper", "--per-lane", "1"]
    try:
        runpy.run_module("scripts.platformkit.bridge_keeper", run_name="__main__")
    except SystemExit as exit_code:
        return int(exit_code.code or 0)
    except Exception as exc:  # a wedged tick must leave a trace, not vanish
        print("watchdog tick failed: %r" % exc)
        return 1
    finally:
        handle.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
