"""Flip stop_requested in live_status.json — bot exits cleanly after current task.

Usage from anywhere:
    python scripts/bot_guards/stop_bot.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import read_json_safe, status_path, write_json_atomic  # noqa: E402

p = status_path()
if not p.exists():
    print("Bot not currently running (no live_status.json).")
    raise SystemExit(0)

s = read_json_safe(p, {})
s["stop_requested"] = True
write_json_atomic(p, s)
print("[stop] flagged. Bot will exit after current task. Use watch.py to confirm.")
