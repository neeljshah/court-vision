#!/usr/bin/env python3
"""
PostToolUse hook — logs file changes to .claude_session_changes.json.
Called automatically by Claude Code on every Write/Edit/Bash tool use.
"""
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
LOG_FILE = os.path.join(PROJECT_DIR, ".claude_session_changes.json")


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Write", "Edit", "Bash", "NotebookEdit"):
        sys.exit(0)

    entry = {
        "time": datetime.now().strftime("%H:%M"),
        "tool": tool_name,
        "file": None,
        "summary": "",
    }

    if tool_name in ("Write", "Edit", "NotebookEdit"):
        file_path = tool_input.get("file_path", tool_input.get("notebook_path", ""))
        if not file_path:
            sys.exit(0)
        # Normalize to forward slashes for readability
        entry["file"] = file_path.replace("\\", "/")
        if tool_name == "Edit":
            old = (tool_input.get("old_string", "") or "")[:60].replace("\n", " ")
            new = (tool_input.get("new_string", "") or "")[:60].replace("\n", " ")
            entry["summary"] = f"Edited: '{old}' → '{new}'"
        else:
            entry["summary"] = f"{tool_name}: created/rewrote file"
    elif tool_name == "Bash":
        cmd = (tool_input.get("command", "") or "")[:150].replace("\n", " ")
        entry["file"] = None
        entry["summary"] = f"Bash: {cmd}"

    # Load and append
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                changes = json.load(f)
        else:
            changes = []
    except Exception:
        changes = []

    changes.append(entry)

    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(changes, f, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    main()
