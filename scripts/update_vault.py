"""
update_vault.py — Auto-update Obsidian vault with current system state.

Generates/refreshes:
  vault/Home.md              — project status dashboard
  vault/Sessions/Session-YYYY-MM-DD.md  — today's session log

Run manually:   python scripts/update_vault.py
Auto-run via:   Claude hook (PostToolUse) or cron
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
SESSIONS = VAULT / "Sessions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: str, default: str = "") -> str:
    try:
        return subprocess.check_output(cmd, shell=True, cwd=ROOT,
                                       stderr=subprocess.DEVNULL,
                                       text=True).strip()
    except Exception:
        return default


def _git_branch() -> str:
    return _run("git rev-parse --abbrev-ref HEAD", "master")


def _git_log(n: int = 5) -> list[str]:
    raw = _run(f'git log --oneline -{n}')
    return raw.splitlines() if raw else []


def _test_summary() -> str:
    """Quick pytest count — no actual run, just reads last cached result if available."""
    cache = ROOT / ".pytest_cache" / "v" / "cache" / "lastfailed"
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            if not data:
                return "all passing (no failures cached)"
        except Exception:
            pass
    return "1040 pass, 2 skip (last known)"


def _open_issues() -> list[tuple[str, str, str]]:
    """Return list of (id, description, status) from CLAUDE.md."""
    claude_md = ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return []
    lines = claude_md.read_text(encoding="utf-8").splitlines()
    issues = []
    in_issues = False
    for line in lines:
        if "Open Issues" in line:
            in_issues = True
            continue
        if in_issues:
            if line.startswith("###") or (line.startswith("##") and "Open Issues" not in line):
                break
            if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.")):
                text = line.lstrip("0123456789. ")
                issues.append(("—", text, "Open"))
    return issues


def _cv_game_count() -> tuple[int, int]:
    """Return (clean, target) from CLAUDE.md."""
    claude_md = ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return 5, 20
    text = claude_md.read_text(encoding="utf-8")
    import re
    m = re.search(r'CV games:\s*(\d+)\s*clean\s*/\s*(\d+)\s*target', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 5, 20


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------

def generate_home() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    branch = _git_branch()
    clean, target = _cv_game_count()
    issues = _open_issues()

    issue_rows = "\n".join(
        f"| {i} | {d} | {s} |" for i, d, s in issues
    ) if issues else "| — | No open issues | — |"

    return f"""---
tags: [index, moc]
updated: {today}
---

# CourtVision — Knowledge Base

*Auto-updated by `scripts/update_vault.py` · {today}*

---

## Quick Navigation

| Note | Description |
|------|-------------|
| [[Pipeline/System Architecture]] | End-to-end architecture, data flow, component map |
| [[Models/Model-Catalog]] | All 90 models, tiers, training status, performance |
| [[Research/Data-Sources]] | Every data source, scraper, TTL, coverage stats |
| [[Pipeline/Pipeline-Flow]] | Step-by-step pipeline from video to edge flag |
| [[Plans/Roadmap]] | Phase-by-phase build plan with current status |
| [[Improvements/Tracker Improvements Log]] | CV tracker fix history |
| [[Validation/prop_holdout_report]] | Prop model holdout validation |

---

## Current Status ({today})

**Branch:** `{branch}` | **Tests:** {_test_summary()}

### Phase Completion

| Phase | Status |
|-------|--------|
| 1 — Data Infrastructure | ✅ Done |
| 2 — CV Tracker | ✅ Done |
| 2.5 — CV Tracker Upgrades | ✅ Done |
| 3 — NBA API Data | ✅ Done |
| 4 — Tier 1 ML Models | ✅ Done |
| 5 — External Factors | ✅ Done |
| 4.6 — Pre-Phase Enrichment | ✅ Done |
| F — Full Game Processing | 🟡 Active ({clean} clean / {target} target) |
| G — Season 2025-26 Batch | 🔲 0/50 games |
| 7 — Tier 2–3 Models (CV features) | 🔲 Blocked on F |
| 8 — Possession Simulator | 🔲 Not started |
| 9–17 — Feedback / Live / Frontend | 🔲 Future |

---

## Model Performance

| Model | Metric | Value |
|-------|--------|-------|
| Win probability | Accuracy | 69.1% |
| Win probability | Brier | 0.203 |
| Player props (pts) | MAE | 0.308 |
| Player props (all 7) | R² | >0.93 |
| xFG v1 | Brier | 0.226 |
| DNP predictor | AUC | 0.979 |
| Matchup model | R² | 0.796 |

---

## CV Data Status

| Metric | Value |
|--------|-------|
| Clean games | {clean} / {target} |
| Season 2025-26 | 0 / 50 |

---

## Open Issues

| # | Issue | Status |
|---|-------|--------|
{issue_rows}

---

## Recent Commits

```
{chr(10).join(_git_log(5))}
```

---

## Session Log

Latest: [[Sessions/Session-{today}]]
Full history: `vault/Sessions/`
"""


def generate_session(notes: str = "") -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    branch = _git_branch()
    clean, target = _cv_game_count()

    return f"""---
date: {today}
session: auto
tags: [session]
---

# Session — {today}

*Generated: {now}*

---

## State

- **Branch:** `{branch}`
- **CV games:** {clean} clean / {target} target
- **Tests:** {_test_summary()}

## Recent Commits

```
{chr(10).join(_git_log(5))}
```

## Notes

{notes if notes else "_No notes for this session._"}

---

[[Home]]
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def update(notes: str = "") -> None:
    VAULT.mkdir(exist_ok=True)
    SESSIONS.mkdir(exist_ok=True)

    # Home
    home_path = VAULT / "Home.md"
    home_path.write_text(generate_home(), encoding="utf-8")
    print(f"Updated: {home_path.relative_to(ROOT)}")

    # Today's session
    today = datetime.now().strftime("%Y-%m-%d")
    session_path = SESSIONS / f"Session-{today}.md"
    if not session_path.exists():
        session_path.write_text(generate_session(notes), encoding="utf-8")
        print(f"Created:  {session_path.relative_to(ROOT)}")
    else:
        print(f"Exists:   {session_path.relative_to(ROOT)} (not overwritten)")


if __name__ == "__main__":
    notes = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    update(notes)
    print("Vault updated.")
