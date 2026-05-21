"""PostToolUse hook — log every bash command for audit (Windows-safe)."""
from __future__ import annotations
import json, os, sys, datetime as dt
from pathlib import Path

if os.environ.get("COURTVISION_BOT_MODE") != "1":
    sys.exit(0)

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cmd = (payload.get("tool_input", {}) or {}).get("command", "")
if not cmd:
    sys.exit(0)

log = Path(".bot_state") / f"bash_log_{dt.date.today().isoformat()}.txt"
log.parent.mkdir(exist_ok=True)
ts = dt.datetime.now().strftime("%H:%M:%S")
truncated = cmd if len(cmd) <= 2000 else cmd[:2000] + f" ...[+{len(cmd)-2000} chars]"
with log.open("a", encoding="utf-8") as f:
    f.write(f"[{ts}] {truncated}\n")
