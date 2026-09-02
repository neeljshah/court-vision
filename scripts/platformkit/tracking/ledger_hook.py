#!/usr/bin/env python
"""PostToolUse(Bash) hook: unforgeable landing count (PLAN_AI_ENGINEERING s2a).

If the Bash command ran `git commit` and the resulting HEAD subject names a gap id
(G<n> or S<n>, optional letter suffix) plus a landing/verdict word, append ONE auto
line to the matching results ledger (G -> tracking ledger, S -> system ledger)
unless that ledger already names the sha. The verifier's full line still follows;
`hook_only > 0` at night means a verifier line is missing.
Exit 0 always -- never blocks a commit. ASCII only. Stdlib only.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path("C:/Users/neelj/nba-ai-system")
LEDGERS = {
    "G": REPO / "docs" / "evidence" / "tracking" / "RESULTS_LEDGER.md",
    "S": REPO / "docs" / "evidence" / "RESULTS_LEDGER_SYSTEM.md",
}
ID_RE = re.compile(r"\b([GS])(\d{2,3}[a-z]?)\b")
LAND_RE = re.compile(
    r"\b(land(ed|ing)?|ACCEPT|REJECT|CLOSED AT LIMIT|NOT VALIDATED|FALSIFIED|NULL|BEHIND|AHEAD)\b", re.I)
COMMIT_RE = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b")
DASH_C_RE = re.compile(r"\bgit\s+-C\s+([^\s;&|]+)")


def _head(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "log", "-1", "--format=%h%x09%s"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.split("\t", 1) if "\t" in out else None


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    if data.get("tool_name") != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    m_commit = COMMIT_RE.search(cmd)
    if not m_commit:
        return
    m_c = DASH_C_RE.search(cmd[: m_commit.end()])
    cwd = m_c.group(1).strip("'\"") if m_c else (data.get("cwd") or str(REPO))
    head = _head(cwd)
    if not head:
        return
    sha, subject = head
    m_id = ID_RE.search(subject)
    if not m_id or not LAND_RE.search(subject):
        return
    ledger = LEDGERS[m_id.group(1)]
    gid = m_id.group(1) + m_id.group(2)
    if ledger.exists() and sha in ledger.read_text(encoding="utf-8", errors="replace"):
        return
    line = "%s | hook | %s | %s | LANDED (auto; verifier line pending) | %s\n" % (
        date.today().isoformat(), gid, subject.replace("|", "/"), sha)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(line)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
