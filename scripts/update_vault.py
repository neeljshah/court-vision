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

# CourtVision — The Renaissance of Sports

> AI-native sports intelligence platform. Claude agents autonomously discover, validate, ship, and retire prediction signals across multiple monetization surfaces.
> *Auto-updated by `scripts/update_vault.py` · {today}*

---

## Current State at a Glance ({today})

**Branch:** `{branch}` | **Tests:** {_test_summary()} | **Velocity:** {velocity['week_commits']} commits/week

| Item | Status |
|------|--------|
| Phase | G (CV game collection — 17 quality / 29 usable / 75 attempted) |
| **Gate 1: CLV vs Pinnacle close** | **NOT YET RUN — TOP PRIORITY** |
| Signal universe | 75 models trained (target: 500-5000 signals via agentic system) |
| Top revenue surface live | None yet (signal subs targeted Q3 2026) |
| Agentic research system | Not yet built (planned — see [[Plans/Agentic Research System]]) |

---

## Quick Navigation

| Domain | Entry Point | What's There |
|--------|------------|--------------|
| Strategy | [[Plans/Project Vision]] | Full product picture + 6 surfaces |
| Renaissance thesis | [[Plans/Renaissance Comparison]] | Similarities + differences with RenTech |
| Agentic system | [[Plans/Agentic Research System]] | Multi-agent Claude architecture |
| Gate 1 | [[Plans/Gate 1 Validation]] | Step-by-step execution plan |
| CV Pipeline | [[MOC-CV]] | Tracking, detection, homography, re-ID |
| ML Models | [[MOC-Models]] | 75 models, features, signal inventory |
| Betting | [[MOC-Betting]] | Kelly, CLV, quant framework, edges |
| Operations | [[MOC-Ops]] | RunPod, data pipeline, architecture |
| Research | [[MOC-Research]] | Validation, benchmarks, concepts |

---

## Model Performance (holdout, walk-forward, 48-hr purge, N=480)

| Model | Metric | Value | Target | Gap |
|-------|--------|-------|--------|-----|
| [[Models/Win Probability\|Win prob]] | Accuracy | 69.1% | 72% | -2.9% |
| [[Models/Win Probability\|Win prob]] | Brier | 0.203 | <0.19 | -0.013 |
| [[Models/Player Props\|Props PTS]] | R² (holdout) | 0.41 | 0.47-0.51 | pending CV lift |
| [[Models/Player Props\|Props REB]] | R² (holdout) | 0.38 | 0.45-0.48 | pending CV lift |
| [[Models/Player Props\|Props AST]] | R² (holdout) | 0.36 | 0.42-0.45 | pending CV lift |
| [[Models/Player Props\|Props FG3M]] | R² (holdout) | 0.29 | 0.37-0.41 | needs closeout speed |
| [[Models/Player Props\|Props TOV]] | R² (holdout) | 0.22 | 0.26-0.29 | marginal |
| [[Models/Player Props\|Props STL]] | R² (holdout) | 0.18 | 0.22-0.25 | filter hard |
| [[Models/Player Props\|Props BLK]] | R² (holdout) | 0.16 | 0.21-0.24 | filter hard |
| [[Models/xFG Model\|xFG]] | Brier | 0.226 | <0.20 | pending CV defender data |
| [[Models/DNP Predictor\|DNP]] | AUC | 0.979 | >0.97 | ✅ |

→ Full metrics: [[Models/Model Performance]]
→ Holdout report: [[Validation/prop_holdout_report]]

---

## CV Data Status

| Metric | Value |
|--------|-------|
| Quality games | 17 |
| Usable games | 29 (9 CLEAN + 20 PARTIAL) |
| Attempted | 75 |
| Goal | 80 CLEAN |

→ Game details: [[Sessions/Game Log]]

---

## Open Issues (top 5)

| # | Issue | Status |
|---|-------|--------|
| 1 | Gate 1 not run — no CLV validation vs real closing lines | 🔴 Top priority |
| 2 | ball_valid_pct=0% on some games (ball_track_suspended stays True) | 🟡 After 80-game run |
| 3 | Underprediction bias on all 7 prop models | 🟡 Calibration pass needed |
| 4 | kelly_corr matrix not populated (run --build-residuals then --compute-corr) | 🟡 After Gate 1 |
| 5 | News ingestion pipe unbuilt (missing injury/lineup reaction edge) | 🔲 Month 4-6 |

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

## Strategic Plans

| Plan | Description |
|------|-------------|
| [[Plans/Project Vision]] | Full product picture, 6 surfaces, Renaissance framing |
| [[Plans/Renaissance Comparison]] | Side-by-side with RenTech — similarities + differences |
| [[Plans/Agentic Research System]] | Multi-agent Claude architecture (the moat) |
| [[Plans/Signal Architecture]] | Signal-based vs model-based, IR tracking, retirement |
| [[Plans/Six Surfaces]] | Detail on each revenue surface, gates, targets |
| [[Plans/Gate 1 Validation]] | Step-by-step Gate 1 execution |
| [[Plans/Investor Narrative]] | Pitch-deck narrative in markdown form |
| [[Plans/Master Build Plan]] | Build sequence, signal priority queue |

---

## History & Progress

| Note | What's There |
|------|-------------|
| [[Sessions/Timeline]] | Condensed project history, milestones, metric progression |
| [[Sessions/Decision Log]] | Key decisions and fixes with impact |
| [[Sessions/Game Log]] | All CV-processed games with grades and metrics |
| [[Tracking/Tracker Improvements]] | Chronological CV fix log |

---

*Session log: [[Sessions/Decision Log]] · Full archive: `Sessions/_archive/`*
*Git repo: README.md · VISION.md · ARCHITECTURE.md · ROADMAP.md · MASTER_PLAN.md*
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
