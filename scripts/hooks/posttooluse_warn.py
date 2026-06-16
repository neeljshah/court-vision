#!/usr/bin/env python
"""PostToolUse warn hook (NOT wired -- proposed).

Reads the Claude Code PostToolUse stdin JSON contract:
  {session_id, cwd, hook_event_name, tool_name, tool_input:{file_path|...}}

WARN mechanism (documented, non-blocking): exit code 0 with the warning
text on stderr. (We deliberately do NOT emit {"decision":"block"} here --
this hook only warns; the human stays in control.)

Warns on Edit|Write when:
  - the edited file exceeds 300 LOC (repo invariant: <=300 LOC/file), or
  - the path falls under a HUMAN-GATED tree:
      src/ kernel/ api/ scripts/team_system/ intel/

ASCII only. Idempotent: pure function of stdin + a read-only line count.
"""
import json
import os
import re
import sys

MAX_LOC = 300
GATED_PREFIXES = (
    "src/",
    "kernel/",
    "api/",
    "scripts/team_system/",
    "intel/",
)


def _warn(msg):
    sys.stderr.write("WARN: " + msg + "\n")


def _rel_norm(path, cwd):
    """Return a forward-slash relative path for prefix matching."""
    p = path.replace("\\", "/")
    if cwd:
        c = cwd.replace("\\", "/").rstrip("/")
        low_p, low_c = p.lower(), c.lower()
        if low_p.startswith(low_c + "/"):
            p = p[len(c) + 1:]
    # collapse any leading repo-root absolute drive prefix to a tail match
    m = re.search(r"nba-ai-system/(.*)$", p, re.IGNORECASE)
    if m:
        p = m.group(1)
    return p.lstrip("/")


def _loc(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except (OSError, IOError):
        return None


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        sys.exit(0)

    if data.get("tool_name") not in ("Edit", "Write"):
        sys.exit(0)

    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    if not path:
        sys.exit(0)

    cwd = data.get("cwd") or ""
    rel = _rel_norm(path, cwd)

    for pref in GATED_PREFIXES:
        if rel.lower().startswith(pref):
            _warn("HUMAN-GATED path `" + rel + "` (under " + pref +
                  "). Edits here require human review before enabling.")
            break

    n = _loc(path)
    if n is not None and n > MAX_LOC:
        _warn("file `" + rel + "` is " + str(n) + " LOC (> " +
              str(MAX_LOC) + " LOC invariant). Consider splitting.")

    # always exit 0 -- warn only, never block
    sys.exit(0)


if __name__ == "__main__":
    main()
