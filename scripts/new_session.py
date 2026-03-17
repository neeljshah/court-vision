#!/usr/bin/env python3
"""
SessionStart hook — creates today's Obsidian session note pre-filled with
context from the last session's 'What's Next' and current open issues.
Also resets the session change log.
"""
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
VAULT_SESSIONS = os.path.join(PROJECT_DIR, "vault", "Sessions")
LOG_FILE = os.path.join(PROJECT_DIR, ".claude_session_changes.json")
IMPROVEMENTS_LOG = os.path.join(PROJECT_DIR, "vault", "Improvements", "Tracker Improvements Log.md")


def get_last_session_info():
    """Return (date, what_next) from most recent session note."""
    try:
        sessions = sorted(
            [f for f in os.listdir(VAULT_SESSIONS) if f.startswith("Session-") and f.endswith(".md")]
        )
    except Exception:
        return None, "No previous session."

    if not sessions:
        return None, "No previous session."

    last_name = sessions[-1]
    last_date = last_name.replace("Session-", "").replace(".md", "")
    last_path = os.path.join(VAULT_SESSIONS, last_name)

    try:
        with open(last_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return last_date, "Could not read last session."

    what_next = "Not specified."
    if "## What's Next" in content:
        section = content.split("## What's Next")[1]
        if "##" in section:
            section = section.split("##")[0]
        what_next = section.strip() or "Not specified."

    return last_date, what_next


def get_open_issues():
    """Return priority queue lines from improvements log."""
    try:
        with open(IMPROVEMENTS_LOG, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    if "## Priority Queue" not in content:
        return []

    section = content.split("## Priority Queue")[1]
    if "##" in section:
        section = section.split("##")[0]

    return [
        line.strip()
        for line in section.strip().splitlines()
        if line.strip() and line.strip()[0].isdigit()
    ][:5]


def main():
    # Reset the change log at session start
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass

    date_str = datetime.now().strftime("%Y-%m-%d")
    session_file = os.path.join(VAULT_SESSIONS, f"Session-{date_str}.md")

    if os.path.exists(session_file):
        # Already exists (multiple starts same day) — just print and exit
        print(f"Session note already exists: Session-{date_str}.md")
        return

    last_date, last_next = get_last_session_info()
    issues = get_open_issues()

    issues_block = "\n".join(f"- {i}" for i in issues) if issues else "- (none logged)"
    last_context = (
        f"*From session {last_date}:*\n\n{last_next}"
        if last_date
        else last_next
    )

    content = f"""# Session — {date_str}

## Goal For This Session
<!-- What are you trying to accomplish today? -->


## Context Going In
{last_context}

## Open Priority Issues
{issues_block}

---

## What Was Done
<!-- Claude logs file changes at session end — add your own notes here -->

1.
2.
3.

## Code Changed

| File | What Changed |
|------|-------------|
|  |  |

## Issues Found
<!-- New bugs or problems discovered this session -->


## Improvements Made
<!-- Fixes applied — also copy to Improvements Log -->


## What's Next
<!-- What to work on next session -->


---
*Session note auto-created by new_session.py*
"""

    try:
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Session note created: Session-{date_str}.md")
    except Exception as e:
        print(f"Warning: could not create session note: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
