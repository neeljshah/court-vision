#!/usr/bin/env python3
"""
Stop hook — finalizes the Obsidian session note, updates CLAUDE.md, and refreshes Home.md.
Called automatically when Claude Code finishes a session (Stop event).
"""
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
VAULT_SESSIONS = os.path.join(PROJECT_DIR, "vault", "Sessions")
LOG_FILE = os.path.join(PROJECT_DIR, ".claude_session_changes.json")
IMPROVEMENTS_LOG = os.path.join(PROJECT_DIR, "vault", "Improvements", "Tracker Improvements Log.md")
CLAUDE_MD = os.path.join(PROJECT_DIR, "CLAUDE.md")
HOME_MD = os.path.join(PROJECT_DIR, "vault", "00 - Home.md")

AUTO_START = "<!-- AUTO-GENERATED — DO NOT EDIT BELOW THIS LINE -->"
AUTO_END = "<!-- END AUTO-GENERATED -->"


def load_changes():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_open_issues():
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


def get_src_status():
    """Scan src/ for module status (empty vs has code)."""
    src_dir = os.path.join(PROJECT_DIR, "src")
    status = {}
    if not os.path.exists(src_dir):
        return status

    for root, _dirs, files in os.walk(src_dir):
        for fname in sorted(files):
            if fname.endswith(".py") and fname != "__init__.py":
                path = os.path.join(root, fname)
                try:
                    size = os.path.getsize(path)
                    rel = os.path.relpath(path, PROJECT_DIR).replace("\\", "/")
                    status[rel] = "✅" if size > 300 else "🔲"
                except Exception:
                    pass
    return status


def get_what_next(date_str):
    """Read 'What's Next' from today's session note."""
    session_file = os.path.join(VAULT_SESSIONS, f"Session-{date_str}.md")
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    if "## What's Next" not in content:
        return None

    section = content.split("## What's Next")[1]
    if "##" in section:
        section = section.split("##")[0]

    text = section.strip()
    # Ignore placeholder lines
    if not text or text.startswith("<!--") or text == "<!-- What to work on next session -->":
        return None
    return text


def get_recent_sessions(n=5):
    """Return list of (date_str, filename) for the n most recent sessions."""
    try:
        sessions = sorted(
            [f for f in os.listdir(VAULT_SESSIONS) if f.startswith("Session-") and f.endswith(".md")],
            reverse=True,
        )
    except Exception:
        return []
    return [s.replace("Session-", "").replace(".md", "") for s in sessions[:n]]


def update_session_note(changes, date_str):
    session_file = os.path.join(VAULT_SESSIONS, f"Session-{date_str}.md")
    if not os.path.exists(session_file):
        return

    changed_files = list(dict.fromkeys(c["file"] for c in changes if c.get("file")))
    bash_cmds = [c["summary"] for c in changes if c["tool"] == "Bash"]

    now = datetime.now().strftime("%H:%M")
    block = f"\n---\n## Auto-logged at {now}\n\n"

    if changed_files:
        block += "**Files changed:**\n"
        for f in changed_files:
            block += f"- `{f}`\n"
    else:
        block += "**Files changed:** none\n"

    if bash_cmds:
        block += "\n**Commands run:**\n"
        for cmd in bash_cmds[:10]:
            block += f"- {cmd}\n"

    try:
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception as e:
        print(f"Warning: could not update session note: {e}", file=sys.stderr)


def update_claude_md(changes, date_str):
    if not os.path.exists(CLAUDE_MD):
        return

    try:
        with open(CLAUDE_MD, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return

    changed_files = list(dict.fromkeys(c["file"] for c in changes if c.get("file")))
    issues = get_open_issues()
    src_status = get_src_status()
    what_next = get_what_next(date_str)
    now = datetime.now().strftime("%H:%M")

    lines = [AUTO_START, ""]
    lines.append(f"## Resume From Here — Last Updated: {date_str} {now}")
    lines.append("")

    # What to work on next — the critical piece for continuity
    lines.append("### Pick Up Where We Left Off")
    if what_next:
        for line in what_next.splitlines():
            lines.append(line)
    else:
        lines.append("*(Fill in '## What's Next' in today's session note before closing)*")
    lines.append("")

    lines.append("### This Session — Files Changed")
    if changed_files:
        for f in changed_files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- No file changes this session")
    lines.append("")

    lines.append("### Open Priority Issues")
    for issue in issues:
        lines.append(f"- {issue}")
    if not issues:
        lines.append("- (none logged)")
    lines.append("")

    lines.append("### Analytics Module Status (src/)")
    for path, icon in sorted(src_status.items()):
        lines.append(f"- {icon} `{path}`")
    if not src_status:
        lines.append("- (src/ not found)")
    lines.append("")

    lines.append(f"### Session Log")
    lines.append(f"- Latest: `vault/Sessions/Session-{date_str}.md`")
    lines.append(f"- Full log: `vault/Sessions/`")
    lines.append("")

    lines.append(AUTO_END)
    auto_block = "\n".join(lines) + "\n\n"

    if AUTO_START in content:
        start_idx = content.index(AUTO_START)
        end_idx = content.index(AUTO_END) + len(AUTO_END)
        while end_idx < len(content) and content[end_idx] == "\n":
            end_idx += 1
        content = content[:start_idx] + auto_block + content[end_idx:]
    else:
        content = auto_block + content

    try:
        with open(CLAUDE_MD, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Warning: could not update CLAUDE.md: {e}", file=sys.stderr)


def update_home_md(changes, date_str):
    """Rewrite Home.md as a live auto-generated dashboard."""
    changed_files = list(dict.fromkeys(c["file"] for c in changes if c.get("file")))
    issues = get_open_issues()
    src_status = get_src_status()
    what_next = get_what_next(date_str)
    recent_sessions = get_recent_sessions(5)
    now = datetime.now().strftime("%H:%M")

    # Build status table rows — BasketTracking modules are always working
    base_modules = [
        ("Player detection (Detectron2)", "✅"),
        ("Ball tracking (Hough + CSRT)", "✅"),
        ("Court rectification (homography)", "✅"),
        ("Video processing loop", "✅"),
    ]
    src_rows = [(os.path.basename(p).replace(".py", "").replace("_", " ").title(), icon)
                for p, icon in sorted(src_status.items())]

    status_table = "| Module | Status |\n|--------|--------|\n"
    for name, icon in base_modules + src_rows:
        status_table += f"| {name} | {icon} |\n"

    # Recent sessions list
    session_links = "\n".join(
        f"- [[Sessions/Session-{d}]]" for d in recent_sessions
    ) or "- (none yet)"

    # Open issues
    issues_block = "\n".join(f"- {i}" for i in issues) or "- (none logged)"

    # What's next
    next_block = what_next or "*(fill in 'What's Next' in today's session note)*"

    # Last session changes
    changes_block = (
        "\n".join(f"- `{f}`" for f in changed_files)
        if changed_files else "- no file changes"
    )

    content = f"""# NBA AI System — Home
*Auto-updated: {date_str} {now}*

---

## Pick Up Here Next Session
{next_block}

---

## Last Session Changes ({date_str})
{changes_block}

---

## Open Priority Issues
{issues_block}

---

## Project Status
{status_table}
---

## Recent Sessions
{session_links}

---

## Quick Links
- [[Improvements/Tracker Improvements Log]] — all issues & fixes
- [[Sessions/Session-{date_str}]] — today's session
- [[Pipeline/System Architecture]] — how everything connects

---
*This file is auto-generated by finalize_session.py — do not edit manually*
"""

    try:
        with open(HOME_MD, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Warning: could not update Home.md: {e}", file=sys.stderr)


def clear_log():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    changes = load_changes()

    update_session_note(changes, date_str)
    update_claude_md(changes, date_str)
    update_home_md(changes, date_str)
    clear_log()

    print(f"Session finalized: {len(changes)} changes logged.")


if __name__ == "__main__":
    main()
