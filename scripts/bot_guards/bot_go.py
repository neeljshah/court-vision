"""bot go -- enable the CourtVisionBot scheduled task and start the autonomous bot.

The bot runs as a Windows scheduled task that fires a fresh headless Claude Code
cycle every 15 min. This script just turns that task ON and kicks the first cycle.

Usage from anywhere:
    python scripts/bot_guards/bot_go.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import read_json_safe, status_path, write_json_atomic  # noqa: E402

TASK = "CourtVisionBot"

# 1. Clear the stop flag so cycles do real work.
p = status_path()
s = read_json_safe(p, {}) if p.exists() else {}
s["stop_requested"] = False
write_json_atomic(p, s)
print("[go] stop flag cleared.")

# 2. Enable the Windows scheduled task.
try:
    r = subprocess.run(
        ["schtasks", "/Change", "/TN", TASK, "/ENABLE"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        print(f"[go] {TASK} scheduled task ENABLED.")
    else:
        print(f"[go] ERROR enabling task: {(r.stderr or r.stdout).strip()}")
        print("[go] The task may not be installed. See scripts/bot_cycle.ps1.")
        raise SystemExit(1)
except FileNotFoundError:
    print("[go] ERROR: schtasks not found on PATH.")
    raise SystemExit(1)

# 3. Kick an immediate first cycle so the bot starts now, not in up to 15 min.
try:
    subprocess.run(
        ["schtasks", "/Run", "/TN", TASK],
        capture_output=True, text=True, timeout=30,
    )
    print("[go] first cycle kicked off now.")
except Exception as e:  # noqa: BLE001
    print(f"[go] note: couldn't kick an immediate run ({e}); it starts within 15 min anyway.")

print("[go] Bot is ON. A fresh headless cycle runs every 15 min -- hands-off.")
print("[go] You can close every window and the bot keeps running while the PC is on.")
print("[go] Stop it any time with: bot stop")
