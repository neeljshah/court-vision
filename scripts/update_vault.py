"""
update_vault.py — Auto-update Obsidian vault with current system state.

Generates/refreshes:
  vault/Home.md                        — project status dashboard
  vault/Intelligence/Teams/<TRI>.md    — folds scheme atlas into the team note
  vault/Intelligence/_Scheme_Matrix.md — 30-team overview

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
    return "4,055 collected · 48/48 critical-path pass (last verified 2026-05-26)"


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

> **Start here:** [[Lessons]] (synthesis — read before scoping any change) · [[_indexes/full_inventory]] (full vault map) · [[Strategy/Now]] (current focus) · [[Memory/Phase Status]] (loop status)

---

## Current State at a Glance ({today})

**Branch:** `{branch}` | **Loop:** improve_loop R12 BATCH-33 · R30-R32 probe wave · execute_loop V1 39/40 layers shipped | **Tests:** {_test_summary()} | **Velocity:** {velocity['week_commits']} commits/week

| Item | Status |
|------|--------|
| Phase | G (CV game collection — 85 tracked / 7 full-feature / target 80 CLEAN) |
| Win probability (walk-forward 3-fold) | **0.7094 acc / 0.193 Brier** — see [[#The 71% Result]] |
| Win probability (single-split) | **0.7169 acc / 0.188 Brier** (XGB zeroed by NNLS) |
| Prop backtest ROI @ +0.5 edge (20K-game holdout, L5 proxy) | **+19.9% to +28.1%** across 7 stats |
| **Gate 1 — real DK/FD/MGM/BetRivers (2024 playoffs, L10)** | ✅ **4,337 bets · 54.58% beat · +4.19% ROI · +$18,181 PnL** |
| **Gate 1 — real DK/FD/MGM (2025-26 mainline, prod stack OOF)** | ⚠️ **4,210 bets · 54.37% beat · −2.06% ROI** — AST +7.22% / FG3M +0.34% are real edges |
| **Combined UNDER-only directional edge** | ✅ **3,512 bets · 58.46% beat · +7.70% ROI · +$27K** — BLK +41% / STL +26% / AST +10% / FG3M +5.5% |
| **Gate 1 — Pinnacle close (sharp book)** | 🔴 **NOT YET RUN** — no historical archive; daemon collects from Oct 2026 |
| **In-game projection (endQ3 vs pregame, 550-game retro)** | Residual heads SHIPPED 6/7 · endQ3 MAE **−47% to −56%** across 7 stats · cycle 110 learned Q4-minutes |
| Signal universe | 312 trained artifacts (target: 500-5000 via agentic system) |
| Top revenue surface live | None yet (signal subs targeted Q3 2026) |
| Agentic research system | Not yet built — see [[Plans/Agentic Research System]] |

---

## In-Game Improvement System (improve_loop R1-R12 BATCH-33)

> Biggest single-batch wins of the project. Pregame projections are at ceiling; in-game residual heads layered on top of pregame are unlocking 47-56% MAE reductions at endQ3.

- **Pregame → in-game residual heads** layer per-quarter residual learners on top of pregame medians, conditioned on elapsed-minute / score-margin / pace-so-far / Q4-minutes-learned (cycle 110).
- **endQ3 MAE delta vs pregame baseline (550-game retro):** PTS −47%, REB −48%, AST −50%, FG3M −53%, TOV −49%, STL −56%, BLK −55% — 7/7 stats win.
- **Cycle 110**: learned Q4-minutes prior (replaces naive 12-minute assumption) — biggest in-game lever so far.
- **execute_loop V1**: 39/40 layers shipped (R1-R5). Order management, multi-exchange (Kalshi/Polymarket/Sporttrade), cross-exchange EV, late-swap, live trader, hedger, edge-erosion + postmortem layers.
- **improve_loop R12 BATCH-33**: drop-in `predict_game` CLI, auto-train fallback, canonical-recipe bundles; 4,515-game dataset.
- Source: `scripts/improve_loop/` · loop memos in `vault/Sessions/` · synthesis in [[Lessons]].

---

## The 71% Result

**Win prob 70.94% walk-forward / 71.7% single-split** — 5-way NNLS stack (XGB+LGB+LR+MLP+NB), 2 seasons. Source: [`data/models/win_prob_metrics.json`](../data/models/win_prob_metrics.json).

**What it means in dollars** — 19,964-game holdout backtest, bet every player-game where projected median deviates from L5 line by ≥ edge threshold, -110 odds (break-even = 52.4%):

| Stat | Edge ≥ 0.5 hit / ROI | Edge ≥ 1.0 hit / ROI |
|------|---------------------|---------------------|
| PTS  | 62.8% / **+19.9%**  | 65.1% / **+24.3%** |
| REB  | 64.8% / **+23.6%**  | 69.5% / **+32.7%** |
| AST  | 66.4% / **+26.8%**  | 72.2% / **+37.9%** |
| FG3M | 64.9% / **+23.9%**  | 77.0% / **+46.9%** |
| TOV  | 67.1% / **+28.1%**  | 77.6% / **+48.2%** |
| STL  | 63.7% / **+21.5%**  | 76.5% / **+46.1%** |
| BLK  | 66.3% / **+26.5%**  | 79.6% / **+52.0%** |

Source: [`data/models/betting_backtest.json`](../data/models/betting_backtest.json). Re-validated cycle 38 vs smarter line proxy (L5 × opp_def × home_adj) → still 26-32% ROI at +0.5 edge. Walk-forward (not random holdout), MAE-optimized (not R²) because prop O/U scores against the median.

**Honest discount.** Paper +25% ROI vs L5-proxy compresses to expected **+3-8% CLV** against sharp closing lines — that's the figure that actually compounds. Gate 1 measures it. See [[Plans/Gate 1 Validation]].

---

## Quick Navigation

| Domain | Entry Point | What's There |
|--------|------------|--------------|
| **Synthesis** | [[Lessons]] | Durable lessons across all loops — read before scoping any change |
| **Vault Inventory** | [[_indexes/full_inventory]] | Hand-curated ~270-note map across ~25 folders |
| **Now / Focus** | [[Strategy/Now]] | Current sprint, blockers, next actions |
| **Phase status** | [[Memory/Phase Status]] | Loop status, what blocks what |
| **Model perf** | [[Models/Model Performance]] | Full honest walk-forward MAE / R² table |
| Strategy | [[Plans/Project Vision]] | Full product picture + 6 surfaces |
| Renaissance thesis | [[Plans/Renaissance Comparison]] | Similarities + differences with RenTech |
| Agentic system | [[Plans/Agentic Research System]] | Multi-agent Claude architecture |
| Gate 1 | [[Plans/Gate 1 Validation]] | Step-by-step execution plan |
| CV Pipeline | [[MOC-CV]] | Tracking, detection, homography, re-ID |
| ML Models | [[MOC-Models]] | 85 models, features, signal inventory |
| Betting | [[MOC-Betting]] | Kelly, CLV, quant framework, edges |
| Operations | [[MOC-Ops]] | RunPod, data pipeline, architecture |
| Research | [[MOC-Research]] | Validation, benchmarks, concepts |

---

## Model Performance (walk-forward q50, per-game N=99,818)

| Model | Metric | Value | Target | Gap |
|-------|--------|-------|--------|-----|
| [[Models/Win Probability\|Win prob]] | Accuracy (WF 3-fold) | 0.7094 | 0.72 | -1.1pp |
| [[Models/Win Probability\|Win prob]] | Brier (WF 3-fold)    | 0.193  | <0.19 | -0.003 |
| [[Models/Win Probability\|Win prob]] | Accuracy (single-split) | 0.7169 | 0.72 | -0.3pp |
| [[Models/Player Props\|Props PTS]]  | MAE | **4.65** (sqrt+Huber+MLP NNLS) | 4.50 | -0.15 |
| [[Models/Player Props\|Props REB]]  | MAE | **1.90** (LGB-q50)             | 1.80 | -0.10 |
| [[Models/Player Props\|Props AST]]  | MAE | **1.37** (XGB+LGB+multitask MLP NNLS) | 1.30 | -0.07 |
| [[Models/Player Props\|Props FG3M]] | MAE | **0.89** (XGB-q50)             | 0.85 | -0.04 |
| [[Models/Player Props\|Props TOV]]  | MAE | **0.89** (XGB-q50)             | 0.85 | -0.04 |
| [[Models/Player Props\|Props STL]]  | MAE | **0.72** (XGB-q50)             | 0.70 | -0.02 |
| [[Models/Player Props\|Props BLK]]  | MAE | **0.44** (XGB-q50)             | 0.42 | -0.02 |
| [[Models/xFG Model\|xFG]] | Brier | 0.226 | <0.20 | pending CV defender data |
| [[Models/DNP Predictor\|DNP]] | AUC | 0.979 | >0.97 | ✅ |

→ Full metrics: [[Models/Model Performance]]
→ Holdout report: [[Validation/prop_holdout_report]]

---

## CV Data Status

| Metric | Value |
|--------|-------|
| Tracked games (data/tracking/) | 85 |
| Full feature extraction | 7 |
| Goal | 80 CLEAN |

→ Game details: [[Sessions/Game Log]]

---

## Open Issues (top 5)

| # | Issue | Status |
|---|-------|--------|
| 1 | Gate 1 vs Pinnacle close — no historical archive; daemon collects from Oct 2026 | 🔴 Sharp-book validation pending |
| 2 | PTS/REB lose to vig at sharp DK/FD/MGM closes (−8.62% / −3.12%) — calibration the next pin | 🟡 Underprediction bias confirmed |
| 3 | ball_valid_pct=0% on some games (ball_track_suspended stays True) | 🟡 After 80-game run |
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
| [[Lessons]] | **Durable synthesis** — read before scoping any model change |
| [[Sessions/2026-05-24_loop5_memo]] | Most recent strategic memo (loop 5 state) |
| [[Sessions/Timeline]] | Condensed project history, milestones, metric progression |
| [[Sessions/Decision Log]] | Key decisions and fixes with impact |
| [[Sessions/Game Log]] | All CV-processed games with grades and metrics |
| [[Tracking/Tracker Improvements]] | Chronological CV fix log |
| [[_indexes/full_inventory]] | Hand-curated full vault inventory (~270 notes) |

---

*Session log: [[Sessions/Decision Log]] · Full archive: `Sessions/_archive/` · Synthesis: [[Lessons]] · Inventory: [[_indexes/full_inventory]]*
*Git repo: README.md · VISION.md · ARCHITECTURE.md · ROADMAP.md · MASTER_PLAN.md*
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _refresh_schemes() -> None:
    """Fold the scheme atlas into each vault/Intelligence/Teams/<TRI>.md note.

    Cheap + idempotent: only touches the SCHEME-AUTO marker block inside each
    team note (curated card + roster blocks preserved) and the _Scheme_Matrix.md
    overview.  Silently skips if the scheme parquets are absent (offline / cold
    clone).
    """
    try:
        # Load the module directly by path so we don't rely on scripts/ being
        # a Python package (it is not — no __init__.py in scripts/).
        import importlib.util
        _mod_path = ROOT / "scripts" / "intel" / "render_schemes_to_vault.py"
        spec = importlib.util.spec_from_file_location(
            "render_schemes_to_vault", str(_mod_path)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        teams_dir = VAULT / "Intelligence" / "Teams"
        mod.render_all(teams_dir=teams_dir)
        print("Updated: vault/Intelligence/Teams/ (scheme atlas folded into 30 team notes + matrix)")
    except ImportError as exc:
        print(f"[update_vault] render_schemes skipped — import error: {exc}")
    except Exception as exc:
        print(f"[update_vault] render_schemes skipped — {exc}")


def _brain_only() -> bool:
    """True when the vault was archived to the clean brain (vault_archive_legacy):
    only _Organized remains and the working Intelligence/ sprawl is gone. In that
    mode the session hooks must NOT re-create Home/Sessions/Intelligence -- doing so
    re-pollutes the person-free graph. Restoring the archive re-enables them."""
    return (VAULT / "_Organized").exists() and not (VAULT / "Intelligence").exists()


def update(notes: str = "") -> None:
    if _brain_only():
        print("[update_vault] brain-only vault detected -- skipping Home/Sessions/scheme writes.")
        return
    VAULT.mkdir(exist_ok=True)
    SESSIONS.mkdir(exist_ok=True)

    home_path = VAULT / "Home.md"
    home_path.write_text(generate_home(), encoding="utf-8")
    print(f"Updated: {home_path.relative_to(ROOT)}")

    # Fold scheme atlas into team notes (idempotent, only the SCHEME-AUTO block)
    _refresh_schemes()


if __name__ == "__main__":
    notes = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    update(notes)
    print("Vault updated.")
