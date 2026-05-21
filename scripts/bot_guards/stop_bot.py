"""bot stop -- disable the CourtVisionBot scheduled task and flag any running cycle to exit.

Usage from anywhere:
    python scripts/bot_guards/stop_bot.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import read_json_safe, status_path, write_json_atomic  # noqa: E402

# 1. Disable the Windows scheduled task so no further 15-min cycles start.
try:
    r = subprocess.run(
        ["schtasks", "/Change", "/TN", "CourtVisionBot", "/DISABLE"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        print("[stop] CourtVisionBot scheduled task DISABLED -- no further cycles will run.")
    else:
        print(f"[stop] note: could not disable scheduled task: {(r.stderr or r.stdout).strip()}")
except Exception as e:  # noqa: BLE001
    print(f"[stop] note: could not disable scheduled task ({e}). Disable it manually in Task Scheduler.")

# 2. Flag any in-progress cycle to exit cleanly after its current task.
p = status_path()
if p.exists():
    s = read_json_safe(p, {})
    s["stop_requested"] = True
    write_json_atomic(p, s)
    print("[stop] stop flag set -- any in-progress cycle exits after its current task.")
else:
    print("[stop] no live_status.json -- nothing in progress.")

print("[stop] Bot is OFF. Re-enable any time with 'bot go'.")
