"""Per-file test for guard_integrity. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_guard_integrity.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ops_sentinel import guard_integrity as gi


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / ".claude" / "rules").mkdir(parents=True)
    (repo / "scripts" / "hooks" / "pretooluse_guard.py").write_text("GUARD v1")
    (repo / ".claude" / "rules" / "no-edge-claims.md").write_text("rule A")
    (repo / "CLAUDE.md").write_text("claude md v1")
    return repo


def test_no_baseline_is_red(tmp_path):
    rows = gi.check_all(repo=_fake_repo(tmp_path),
                        baseline_path=tmp_path / "absent.json")
    assert len(rows) == 1 and rows[0]["status"] == "RED"
    assert rows[0]["reason"] == "no_baseline"


def test_clean_then_tamper_then_accept(tmp_path):
    repo = _fake_repo(tmp_path)
    bp = tmp_path / "baseline.json"
    sp = tmp_path / "status.json"
    ap = tmp_path / "ALERT.json"
    gi.write_baseline(repo=repo, baseline_path=bp, now=1000.0)
    baseline = json.loads(bp.read_text())
    assert len(baseline["files"]) == 3

    rows = gi.tick(now=1010.0, repo=repo, baseline_path=bp,
                   status_path=sp, alarm_path=ap)
    assert all(r["status"] == "GREEN" for r in rows)
    assert not ap.exists()

    # tamper: change the guard hook -> RED row + alarm w/ old+new hash
    guard = repo / "scripts" / "hooks" / "pretooluse_guard.py"
    guard.write_text("GUARD v2 TAMPERED")
    rows = gi.tick(now=1020.0, repo=repo, baseline_path=bp,
                   status_path=sp, alarm_path=ap)
    bad = [r for r in rows if r["status"] == "RED"]
    assert len(bad) == 1 and bad[0]["reason"] == "changed"
    assert bad[0]["name"] == "scripts/hooks/pretooluse_guard.py"
    assert bad[0]["old_sha256"] != bad[0]["new_sha256"]
    alarm = json.loads(ap.read_text())
    assert alarm["mismatches"][0]["name"] == "scripts/hooks/pretooluse_guard.py"
    # the tampered file was NOT reverted (detect-only)
    assert guard.read_text() == "GUARD v2 TAMPERED"
    status = json.loads(sp.read_text())
    assert status["overall"] == "RED"

    # explicit --accept-current path re-baselines; alarm clears on next tick
    gi.write_baseline(repo=repo, baseline_path=bp, now=1030.0)
    rows = gi.tick(now=1040.0, repo=repo, baseline_path=bp,
                   status_path=sp, alarm_path=ap)
    assert all(r["status"] == "GREEN" for r in rows)
    assert not ap.exists()


def test_added_and_missing_rules_files_are_red(tmp_path):
    repo = _fake_repo(tmp_path)
    bp = tmp_path / "baseline.json"
    gi.write_baseline(repo=repo, baseline_path=bp)
    (repo / ".claude" / "rules" / "new-rule.md").write_text("sneaky")
    (repo / ".claude" / "rules" / "no-edge-claims.md").unlink()
    reasons = {r["name"]: r["reason"] for r in
               gi.check_all(repo=repo, baseline_path=bp)}
    assert reasons[".claude/rules/new-rule.md"] == "added"
    assert reasons[".claude/rules/no-edge-claims.md"] == "missing"


def test_real_guarded_files_exist_in_this_repo():
    files = gi.guarded_files()
    names = {p.name for p in files}
    assert "pretooluse_guard.py" in names and "CLAUDE.md" in names
    assert sum(1 for p in files if p.suffix == ".md" and "rules" in str(p)) >= 4
