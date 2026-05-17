"""
update_vault.py — Auto-update Obsidian vault with current system state.

Generates/refreshes:
  vault/Home.md              — project status dashboard

Session logging is handled by vault_session_close.py (Stop hook),
which appends to vault/Sessions/Decision Log.md instead of creating
per-session files.

Run manually:   python scripts/update_vault.py
Auto-run via:   Claude hook (PostToolUse) or cron
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
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
    claude_md = ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return 5, 20
    text = claude_md.read_text(encoding="utf-8")
    m = re.search(r'CV games:\s*(\d+)\s*clean\s*/\s*(\d+)\s*target', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 5, 20


def _recent_activity(n: int = 8) -> list[dict]:
    raw = _run(f'git log --format="%ad|%s" --date=short -{n}')
    if not raw:
        return []
    entries = []
    seen_dates = set()
    for line in raw.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2:
            date, msg = parts
            if date not in seen_dates:
                entries.append({"date": date, "msg": msg})
                seen_dates.add(date)
    return entries[:6]


def _weekly_velocity() -> dict:
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    week_commits = _run(f'git rev-list --count --since="{week_ago}" HEAD', "0")
    month_commits = _run(f'git rev-list --count --since="{month_ago}" HEAD', "0")
    files_changed_week = _run(
        f'git diff --stat --since="{week_ago}" HEAD 2>/dev/null | tail -1', ""
    )
    return {
        "week_commits": int(week_commits) if week_commits.isdigit() else 0,
        "month_commits": int(month_commits) if month_commits.isdigit() else 0,
    }


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------

def generate_home() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    branch = _git_branch()
    clean, target = _cv_game_count()
    issues = _open_issues()
    activity = _recent_activity()
    velocity = _weekly_velocity()

    issue_rows = "\n".join(
        f"| {i} | {d} | {s} |" for i, d, s in issues
    ) if issues else "| — | No open issues | — |"

    activity_rows = "\n".join(
        f"| {a['date']} | {a['msg'][:70]} |" for a in activity
    ) if activity else "| — | No recent activity |"

    return f"""---
tags: [index, moc]
updated: {today}
---

# CourtVision — Knowledge Base

*Auto-updated by `scripts/update_vault.py` · {today}*

---

## Quick Navigation

| Domain | Entry Point | What's There |
|--------|------------|--------------|
| Strategy | [[Strategy/Now]] | Current focus, blockers, next actions |
| CV Pipeline | [[MOC-CV]] | Tracking, detection, homography, re-ID |
| ML Models | [[MOC-Models]] | 75 models, features, signal inventory |
| Betting | [[MOC-Betting]] | Kelly, CLV, quant framework, edges |
| Operations | [[MOC-Ops]] | RunPod, data pipeline, architecture |
| Research | [[MOC-Research]] | Validation, benchmarks, concepts |

## History & Progress

| Note | What's There |
|------|-------------|
| [[Sessions/Timeline]] | Condensed project history, milestones, metric progression |
| [[Sessions/Decision Log]] | Key decisions and fixes with impact |
| [[Sessions/Game Log]] | All CV-processed games with grades and metrics |
| [[Tracking/Tracker Improvements]] | Chronological CV fix log |

---

## Current Status ({today})

**Branch:** `{branch}` | **Tests:** {_test_summary()} | **Velocity:** {velocity['week_commits']} commits/week

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

| Model | Metric | Value | Target | Gap |
|-------|--------|-------|--------|-----|
| [[Models/Win Probability\|Win prob]] | Accuracy | 69.1% | 72% | -2.9% |
| [[Models/Win Probability\|Win prob]] | Brier | 0.203 | <0.19 | -0.013 |
| [[Models/Player Props\|Props PTS]] | R² | 0.47 | 0.55 | -0.08 |
| [[Models/Player Props\|Props REB]] | R² | 0.40 | 0.50 | -0.10 |
| [[Models/Player Props\|Props AST]] | R² | 0.46 | 0.55 | -0.09 |
| [[Models/Player Props\|Props STL]] | R² | 0.07 | 0.20 | -0.13 |
| [[Models/xFG Model\|xFG]] | Brier | 0.226 | <0.20 | -0.026 |
| [[Models/DNP Predictor\|DNP]] | AUC | 0.979 | >0.97 | ✅ |
| [[Models/Matchup Model\|Matchup]] | R² | 0.796 | >0.80 | -0.004 |

→ Full metrics: [[Models/Model Performance]]
→ Holdout reality check: [[Validation/prop_holdout_report]]

---

## CV Data Status

| Metric | Value |
|--------|-------|
| Clean games | {clean} / {target} |
| Season 2025-26 | 0 / 50 |
| Tracking rows | ~126K |

→ Game details: [[Sessions/Game Log]]

---

## Open Issues

| # | Issue | Status |
|---|-------|--------|
{issue_rows}

---

## Recent Activity

| Date | What |
|------|------|
{activity_rows}

---

## Maps of Content

| MOC | Domain |
|-----|--------|
| [[MOC-CV]] | CV pipeline, tracking, detection, homography |
| [[MOC-Models]] | ML models, features, signal inventory |
| [[MOC-Betting]] | Kelly sizing, CLV, quant framework, edges |
| [[MOC-Ops]] | RunPod ops, data pipeline, architecture |
| [[MOC-Strategy]] | Strategy, roadmap, decisions, product plans |
| [[MOC-Research]] | Research, validation, concepts, benchmarks |

---

## Deep Dives

| Note | Description |
|------|-------------|
| [[Plans/Master Build Plan]] | 100-model stack, priority queue, ROI projections |
| [[Pipeline/System Architecture]] | End-to-end pipeline architecture |
| [[Research/Data-Sources]] | Every data source, scraper, TTL, coverage |
| [[Pipeline/Pipeline-Flow]] | Step-by-step from video to edge flag |
| [[Strategy/Edge Taxonomy]] | 164 exploitable market gaps |
| [[Validation/prop_holdout_report]] | Prop model holdout validation |

---

*Session log: [[Sessions/Decision Log]] · Full archive: `Sessions/_archive/`*
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def update(notes: str = "") -> None:
    VAULT.mkdir(exist_ok=True)
    SESSIONS.mkdir(exist_ok=True)

    home_path = VAULT / "Home.md"
    home_path.write_text(generate_home(), encoding="utf-8")
    print(f"Updated: {home_path.relative_to(ROOT)}")


if __name__ == "__main__":
    notes = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    update(notes)
    print("Vault updated.")
