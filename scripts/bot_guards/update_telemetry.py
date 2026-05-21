"""Per-commit telemetry writer — called from workday-loop step 4c.

Runs as part of the merge/push bash chain so it can't be silently skipped the
way the previous "Opus, please call add_spend()" instruction was. Idempotent
per commit SHA — re-running on the same HEAD is a no-op.

Estimates spend from `git show --stat` because the Claude session's true token
count isn't visible from outside the session. The estimate uses CLAUDE.md's
routing rule (30% Opus orchestration + 70% Sonnet implementation) and a
~80-tokens-per-changed-line heuristic. Rough, but enough to see capacity used.
"""
from __future__ import annotations

import json
import subprocess
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "bot_guards"))

from _state import (  # noqa: E402
    add_spend, estimate_usd, read_json_safe, status_path, write_json_atomic,
)

TELEMETRY_LOG = ROOT / ".bot_state" / "telemetry_seen.json"
TOKENS_PER_LINE = 80  # read + reasoning + write per changed line
OPUS_SHARE = 0.30
SONNET_SHARE = 0.70


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _seen(sha: str) -> bool:
    seen = read_json_safe(TELEMETRY_LOG, {"shas": []}).get("shas", [])
    return sha in seen


def _mark_seen(sha: str) -> None:
    data = read_json_safe(TELEMETRY_LOG, {"shas": []})
    data.setdefault("shas", []).append(sha)
    data["shas"] = data["shas"][-200:]  # keep last 200 — bounded growth
    write_json_atomic(TELEMETRY_LOG, data)


def _diff_lines(sha: str) -> int:
    """Total insertions + deletions for one commit (excludes merge-summary)."""
    try:
        out = _git(["show", "--stat", "--format=", sha])
    except subprocess.CalledProcessError:
        return 0
    last = next(
        (ln for ln in reversed(out.splitlines())
         if "insertion" in ln or "deletion" in ln or "changed" in ln),
        "",
    )
    ins = dels = 0
    parts = last.replace(",", "").split()
    for i, p in enumerate(parts):
        if p.startswith("insertion"):
            ins = int(parts[i - 1])
        elif p.startswith("deletion"):
            dels = int(parts[i - 1])
    return ins + dels


def record(sha: str | None = None) -> dict | None:
    sha = sha or _git(["rev-parse", "HEAD"])
    if _seen(sha):
        return None

    subj = _git(["log", "-1", "--format=%s", sha])
    branch_refs = _git(["log", "-1", "--format=%D", sha])
    is_merge = subj.startswith("Merge:") or " " in _git(["log", "-1", "--format=%P", sha])
    is_bot_work = "bot/" in branch_refs or is_merge or subj.startswith(
        ("feat:", "fix:", "chore:", "refactor:", "test:", "docs:")
    )
    if not is_bot_work:
        return None

    changed = _diff_lines(sha)
    if changed == 0 and not is_merge:
        return None

    est_in = changed * TOKENS_PER_LINE
    est_out = max(changed * 20, 500)  # output is smaller; floor for tiny commits
    usd = (
        OPUS_SHARE * estimate_usd(est_in, est_out, "opus")
        + SONNET_SHARE * estimate_usd(est_in, est_out, "sonnet")
    )

    slug = subj[:50]
    spend = add_spend(usd=usd, in_tok=est_in, out_tok=est_out, task_slug=slug)

    if is_merge:
        s = read_json_safe(status_path(), {})
        s["tasks_completed_today"] = int(s.get("tasks_completed_today", 0)) + 1
        s["last_commit"] = sha[:12]
        s["last_update"] = dt.datetime.now().isoformat(timespec="seconds")
        write_json_atomic(status_path(), s)

    _mark_seen(sha)
    return {"sha": sha[:12], "subj": slug, "changed": changed,
            "usd_added": usd, "spend_today": spend}


def backfill(since_iso: str) -> list[dict]:
    """Record telemetry for all unseen commits since the given ISO date.

    Git's `--since YYYY-MM-DD` is unreliable across versions, so we list a wide
    range of recent SHAs and filter by author-date in Python.
    """
    raw = _git(["log", "-200", "--format=%H %aI"]).splitlines()
    out = []
    pairs = [(ln.split(" ", 1)[0], ln.split(" ", 1)[1]) for ln in raw if " " in ln]
    keep = [sha for sha, iso in pairs if iso >= since_iso]
    for sha in reversed(keep):  # oldest first
        r = record(sha)
        if r:
            out.append(r)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        since = sys.argv[2] if len(sys.argv) > 2 else dt.date.today().isoformat()
        results = backfill(since)
        print(json.dumps({"backfilled": len(results), "items": results}, indent=2))
    else:
        r = record()
        print(json.dumps(r or {"skipped": True}, indent=2))
