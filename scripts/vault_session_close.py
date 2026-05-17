"""
vault_session_close.py — End-of-session vault auto-update.

Run by Claude Code Stop hook. Updates:
  1. vault/Home.md — refresh status dashboard
  2. vault/Tracking/Open Issues.md — sync from CLAUDE-state.md
  3. vault/Data/CV Data Status.md — update counts
  4. vault/Models/Model Performance.md — refresh metrics
  5. vault/Sessions/Decision Log.md — append one row per session (idempotent)
  6. vault/Strategy/Now.md — update snapshot date

Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
TODAY = datetime.now().strftime("%Y-%m-%d")
DECISION_LOG = VAULT / "Sessions" / "Decision Log.md"


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, cwd=ROOT,
            stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""


def update_home():
    try:
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from update_vault import update
        update()
    except ImportError:
        subprocess.run(
            ["python", str(ROOT / "scripts" / "update_vault.py")],
            cwd=ROOT, capture_output=True
        )


def update_open_issues():
    state_file = ROOT / "docs" / "CLAUDE-state.md"
    if not state_file.exists():
        return

    text = state_file.read_text(encoding="utf-8")

    issues_section = []
    in_issues = False
    for line in text.splitlines():
        if line.startswith("## Open Issues"):
            in_issues = True
            continue
        if in_issues:
            if line.startswith("## ") and "Open Issues" not in line:
                break
            if line.strip():
                issues_section.append(line)

    if not issues_section:
        return

    target = VAULT / "Tracking" / "Open Issues.md"
    if not target.exists():
        return

    content = target.read_text(encoding="utf-8")
    parts = content.split("# Open Issues")
    if len(parts) < 2:
        return

    new_issues = "\n".join(issues_section)
    new_content = parts[0] + f"""# Open Issues

*Auto-synced from `docs/CLAUDE-state.md` on {TODAY}*

{new_issues}

-> Tracked in `docs/CLAUDE-state.md`
-> Priority aligned with [[Strategy/Build Phases]]
"""
    target.write_text(new_content, encoding="utf-8")


def update_cv_status():
    tracking_dir = ROOT / "data" / "tracking"
    if not tracking_dir.exists():
        return

    game_count = sum(1 for d in tracking_dir.iterdir() if d.is_dir())

    target = VAULT / "Data" / "CV Data Status.md"
    if not target.exists():
        return

    content = target.read_text(encoding="utf-8")
    content = re.sub(
        r"Games processed \| \d+",
        f"Games processed | {game_count}",
        content
    )
    content = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}",
        f"updated: {TODAY}",
        content
    )
    target.write_text(content, encoding="utf-8")


def update_model_performance():
    state_file = ROOT / "docs" / "CLAUDE-state.md"
    if not state_file.exists():
        return

    text = state_file.read_text(encoding="utf-8")

    r2_pattern = r"(\w+)=([\d.]+)"
    r2_matches = re.findall(r2_pattern, text)
    if not r2_matches:
        return

    target = VAULT / "Models" / "Model Performance.md"
    if not target.exists():
        return

    content = target.read_text(encoding="utf-8")
    for stat, value in r2_matches:
        stat_upper = stat.upper()
        pattern = rf"(\[\[Player Props\]\] {stat_upper} \| R.. \| )[\d.]+"
        content = re.sub(pattern, rf"\g<1>{value}", content)

    content = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}",
        f"updated: {TODAY}",
        content
    )
    target.write_text(content, encoding="utf-8")


def update_now_snapshot():
    now_file = VAULT / "Strategy" / "Now.md"
    if not now_file.exists():
        return
    content = now_file.read_text(encoding="utf-8")
    content = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}",
        f"updated: {TODAY}",
        content
    )
    now_file.write_text(content, encoding="utf-8")


def _categorize_commit(msg: str) -> str:
    msg_lower = msg.lower()
    if any(k in msg_lower for k in ["fix", "bug", "crash", "broken"]):
        return "fix"
    if any(k in msg_lower for k in ["feat", "add", "wire", "implement"]):
        return "feature"
    if any(k in msg_lower for k in ["refactor", "cleanup", "reorganize"]):
        return "refactor"
    if any(k in msg_lower for k in ["doc", "readme", "plan"]):
        return "docs"
    if any(k in msg_lower for k in ["test", "spec", "validate"]):
        return "test"
    if any(k in msg_lower for k in ["chore", "gitignore", "config"]):
        return "chore"
    return "other"


def _detect_metric_changes() -> str:
    state_file = ROOT / "docs" / "CLAUDE-state.md"
    if not state_file.exists():
        return "no metric changes detected"

    text = state_file.read_text(encoding="utf-8")
    metrics = []

    for pattern, label in [
        (r"R[²2]\s*[=:]\s*([\d.]+)", "R²"),
        (r"Brier\s*[=:]\s*([\d.]+)", "Brier"),
        (r"MAE\s*[=:]\s*([\d.]+)", "MAE"),
        (r"AUC\s*[=:]\s*([\d.]+)", "AUC"),
    ]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            metrics.append(f"{label}={matches[-1]}")

    if metrics:
        return "metrics: " + ", ".join(metrics[:4])
    return "no metric changes detected"


def _detect_affected_domains() -> list[str]:
    diff_files = _run("git diff --name-only HEAD~1 HEAD 2>/dev/null")
    if not diff_files:
        return []
    domains = set()
    for f in diff_files.splitlines():
        if "tracking" in f or "detection" in f or "homography" in f:
            domains.add("CV")
        if "model" in f or "prediction" in f or "props" in f:
            domains.add("Models")
        if "betting" in f or "kelly" in f or "portfolio" in f:
            domains.add("Betting")
        if "api/" in f or "endpoint" in f:
            domains.add("API")
        if "feature" in f:
            domains.add("Features")
        if "pipeline" in f:
            domains.add("Pipeline")
        if "vault/" in f:
            domains.add("Vault")
    return sorted(domains)


def update_decision_log():
    DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)

    commit_msg = _run("git log --oneline -1")
    if commit_msg:
        parts = commit_msg.split(" ", 1)
        summary = parts[1] if len(parts) > 1 else commit_msg
    else:
        summary = "no commit this session"

    if len(summary) > 80:
        summary = summary[:77] + "..."

    impact = _detect_metric_changes()
    domains = _detect_affected_domains()
    if domains:
        impact = f"{', '.join(domains)} | {impact}"

    new_row = f"| {TODAY} | {summary} | {impact} |"

    if not DECISION_LOG.exists():
        DECISION_LOG.write_text(
            f"""---
tags: [decision-log, moc]
updated: {TODAY}
aliases: ["Decision Log"]
---

> [[Home]] | [[Sessions/Timeline]] | [[Sessions/Game Log]]

# Decision Log

Rolling log of key decisions, fixes, and milestones. Auto-updated by `vault_session_close.py`.
One row per significant event. Full session files in `Sessions/_archive/`.

---

| Date | Key Decision / Fix | Impact |
|------|--------------------|--------|
{new_row}
""",
            encoding="utf-8"
        )
        return

    content = DECISION_LOG.read_text(encoding="utf-8")

    today_pattern = rf"^\| {re.escape(TODAY)} \|.*$"
    if re.search(today_pattern, content, re.MULTILINE):
        content = re.sub(today_pattern, new_row, content, flags=re.MULTILINE)
    else:
        separator = "|------|--------------------|--------|"
        if separator in content:
            content = content.replace(
                separator,
                separator + "\n" + new_row,
                1
            )

    content = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}",
        f"updated: {TODAY}",
        content,
        count=1
    )

    DECISION_LOG.write_text(content, encoding="utf-8")


def main():
    print("vault_session_close: updating vault...")
    update_home()
    update_open_issues()
    update_cv_status()
    update_model_performance()
    update_now_snapshot()
    update_decision_log()
    print("vault_session_close: done")


if __name__ == "__main__":
    main()
