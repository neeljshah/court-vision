"""
log_change.py — PostToolUse hook.
Reads tool-use JSON from stdin and appends file-change entries to the
current session note in vault/Sessions/.

Called by Claude Code after every Write, Edit, Bash, or NotebookEdit.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _session_note_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return PROJECT_DIR / "vault" / "Sessions" / f"Session-{today}.md"


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    # Only log file-modifying operations with a clear path
    file_path = None
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
    elif tool_name == "Bash":
        # Don't log every bash command — too noisy
        return

    if not file_path:
        return

    # Shorten path to be relative to project root
    try:
        rel = os.path.relpath(file_path, str(PROJECT_DIR))
    except ValueError:
        rel = file_path

    note_path = _session_note_path()
    if not note_path.exists():
        return  # session note not created yet — skip

    timestamp = datetime.now().strftime("%H:%M")
    entry = f"- `{rel}` ({tool_name.lower()}) at {timestamp}\n"

    content = note_path.read_text(encoding="utf-8")
    marker = "## Files Changed"
    if marker in content:
        # Append under the ## Files Changed section
        idx = content.index(marker) + len(marker)
        content = content[:idx] + "\n" + entry + content[idx:]
    else:
        content += f"\n{marker}\n{entry}"

    note_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
