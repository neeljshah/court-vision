"""PreToolUse hook — block bot from editing high-risk files / lines.

Reads JSON tool input on stdin per Claude Code hook spec. Exit 2 blocks the call
with the stderr message shown to the model; exit 0 allows.

Two protection modes:
  1. FILE_BLOCKED — whole file off-limits without explicit override.
  2. LINE_GUARDED — file editable, but specific lines/patterns must not change.
     Detected by inspecting tool_input.old_string against guarded constants.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

if os.environ.get("COURTVISION_BOT_MODE") != "1":
    sys.exit(0)

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_input = payload.get("tool_input", {}) or {}
path = (tool_input.get("file_path") or "").replace("\\", "/")
old_str = tool_input.get("old_string") or ""
new_str = tool_input.get("new_string") or ""

FILE_BLOCKED = {
    "src/prediction/betting_portfolio.py",
    "database/schema.sql",
    "CLAUDE.md",
    "requirements.txt",
    "environment.yml",
    ".claude/bot-settings.json",
    "scripts/bot_guards/pre_edit_check.py",
}

# Patterns that must survive untouched even in otherwise-editable files.
LINE_GUARDED = {
    "src/pipeline/unified_pipeline.py": [
        "_VRAM_FLUSH_INTERVAL = 3000",
    ],
}

override = Path(".bot_state/edit_override.txt")
override_text = override.read_text(encoding="utf-8") if override.exists() else ""


def deny(msg: str) -> None:
    print(f"BLOCKED: {msg}", file=sys.stderr)
    sys.exit(2)


for p in FILE_BLOCKED:
    if path.endswith(p):
        if p in override_text:
            sys.exit(0)
        deny(f"{p} is protected. Commit on a branch and add to .planning/queue/for-review.md "
             f"instead of editing directly. To override, write the path into .bot_state/edit_override.txt.")

for guarded_file, guarded_lines in LINE_GUARDED.items():
    if not path.endswith(guarded_file):
        continue
    for line in guarded_lines:
        if line in old_str and line not in new_str:
            if guarded_file in override_text:
                sys.exit(0)
            deny(f"{guarded_file} edit removes landmine constant `{line}`. "
                 f"This value is load-bearing (see CLAUDE.md). Refuse the change or "
                 f"add `{guarded_file}` to .bot_state/edit_override.txt with justification.")

sys.exit(0)
