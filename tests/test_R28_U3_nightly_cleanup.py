"""tests/test_R28_U3_nightly_cleanup.py — R28_U3 cleanup orchestrator tests.

Ship gate: >=10 tests, all pass.

Covers:
  1.  Dry-run produces no deletes (files still on disk).
  2.  --commit deletes only files past threshold.
  3.  min_keep preserves the youngest N regardless of age.
  4.  Per-category isolation (deleting predictions doesn't touch alerts).
  5.  MB-freed math correct.
  6.  Worktree cleanup respects merged-status (NOT merged → not pruned).
  7.  Worktree cleanup prunes merged + old.
  8.  --max-age-days override works.
  9.  Empty target dir is no-op (no error).
 10.  Permission denied is captured as warning + scan continues.
 11.  Symlink not followed (security).
 12.  Protected paths NEVER eligible (data/pnl_ledger.csv etc).
 13.  --category filter limits scan to one category.
 14.  CLI happy-path end-to-end via main() returns 0 + JSON.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import nightly_cleanup as nc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _touch(path: Path, days_old: float = 0.0, size_kb: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (size_kb * 1024))
    if days_old > 0:
        mt = time.time() - days_old * 86400.0
        os.utime(path, (mt, mt))
    return path


def _mk_repo(tmp_path: Path) -> Path:
    """Create a synthetic repo root with data/cache layout."""
    (tmp_path / "data" / "cache").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "cache" / "alerts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "cache" / "daemon_heartbeats").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "cache" / "rec_tracker").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "lines" / "snapshots").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Dry-run produces no deletes
# ---------------------------------------------------------------------------
def test_dry_run_no_deletes(tmp_path):
    root = _mk_repo(tmp_path)
    # 10 files >30d so min_keep=7 leaves 3 eligible.
    for i in range(10):
        _touch(root / f"data/cache/predictions_cache_2024-01-{i:02d}.parquet",
               days_old=40.0 + i, size_kb=10)
    res = nc.run_cleanup(root=root, commit=False, include_worktrees=False,
                         only_category="predictions")
    # Dry-run reports eligibility but files are intact.
    for p in root.glob("data/cache/predictions_cache_*.parquet"):
        assert p.exists()
    assert res["per_category"]["predictions"]["n_eligible"] == 3


# ---------------------------------------------------------------------------
# 2. --commit deletes only files past threshold
# ---------------------------------------------------------------------------
def test_commit_deletes_only_past_threshold(tmp_path):
    root = _mk_repo(tmp_path)
    # min_keep=7 for predictions — make 10 files, 5 old (>30d), 5 fresh.
    old_files = []
    for i in range(5):
        p = _touch(root / f"data/cache/predictions_cache_2024-01-{i:02d}.parquet",
                   days_old=40.0 + i, size_kb=1)
        old_files.append(p)
    fresh_files = []
    for i in range(5):
        p = _touch(root / f"data/cache/predictions_cache_2026-01-{i:02d}.parquet",
                   days_old=float(i), size_kb=1)
        fresh_files.append(p)
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    # min_keep=7 means 7 youngest are protected. We have 10 files, threshold>30.
    # 5 are <30d (kept naturally), 5 are >30d. Of those 5 old ones, the 2 youngest
    # (40d, 41d) overlap with min_keep=7 (5 fresh + 2 oldest of the old). Actually
    # min_keep sorts by age asc, so youngest 7 = 5 fresh + 2 oldest-of-old (40,41).
    # Therefore the 3 oldest (42,43,44d) get deleted.
    surviving_old = [p for p in old_files if p.exists()]
    surviving_fresh = [p for p in fresh_files if p.exists()]
    assert len(surviving_fresh) == 5
    assert len(surviving_old) == 2  # 40d + 41d saved by min_keep
    assert res["per_category"]["predictions"]["n_eligible"] == 3


# ---------------------------------------------------------------------------
# 3. min_keep preserves the youngest N regardless of age
# ---------------------------------------------------------------------------
def test_min_keep_preserves_youngest(tmp_path):
    root = _mk_repo(tmp_path)
    # All 10 files >>30 days old, but min_keep=7 should save the 7 youngest.
    for i in range(10):
        _touch(root / f"data/cache/predictions_cache_y{i:02d}.parquet",
               days_old=100.0 + i, size_kb=1)
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    assert res["per_category"]["predictions"]["n_eligible"] == 3  # 10-7
    remaining = list(root.glob("data/cache/predictions_cache_*.parquet"))
    assert len(remaining) == 7


# ---------------------------------------------------------------------------
# 4. Per-category isolation
# ---------------------------------------------------------------------------
def test_per_category_isolation(tmp_path):
    root = _mk_repo(tmp_path)
    # 10 old predictions + 10 old alerts.
    for i in range(10):
        _touch(root / f"data/cache/predictions_cache_a{i:02d}.parquet",
               days_old=50.0 + i, size_kb=1)
        _touch(root / f"data/cache/alerts/critical_2024-{i:02d}.json",
               days_old=30.0 + i, size_kb=1)
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    # Predictions touched, alerts untouched.
    assert len(list(root.glob("data/cache/predictions_cache_*.parquet"))) == 7
    assert len(list(root.glob("data/cache/alerts/critical_*.json"))) == 10
    assert "alerts" not in res["per_category"]


# ---------------------------------------------------------------------------
# 5. MB-freed math correct
# ---------------------------------------------------------------------------
def test_mb_freed_math(tmp_path):
    root = _mk_repo(tmp_path)
    # 8 files at 100KB each, all 100 days old. min_keep=7 → 1 deleted = 100KB.
    for i in range(8):
        _touch(root / f"data/cache/predictions_cache_m{i:02d}.parquet",
               days_old=100.0 + i, size_kb=100)
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    info = res["per_category"]["predictions"]
    assert info["n_eligible"] == 1
    # 100KB == ~0.0977 MB. Tolerate float fuzz.
    assert 0.09 < info["mb_eligible"] < 0.11


# ---------------------------------------------------------------------------
# 6. Worktree cleanup respects merged status
# ---------------------------------------------------------------------------
def test_worktree_not_merged_not_pruned(tmp_path):
    root = _mk_repo(tmp_path)
    wt_root = root / ".claude" / "worktrees"
    wt = wt_root / "agent-abc123"
    wt.mkdir(parents=True)
    # Mtime > 3 days.
    old = time.time() - 10 * 86400.0
    os.utime(wt, (old, old))

    def fake_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
        if args[:2] == ["worktree", "list"]:
            return 0, f"worktree {wt.as_posix()}\nbranch refs/heads/feat-x\n\n", ""
        if args[:2] == ["branch", "--merged"]:
            return 0, "* master\n", ""  # feat-x NOT in merged set.
        if args[:2] == ["worktree", "remove"]:
            raise AssertionError("should not be called when not merged")
        return 1, "", "unknown"
    out = nc.cleanup_worktrees(repo_root=root, age_days=3, commit=True,
                               git_runner=fake_git)
    assert out["n_pruned"] == 0
    assert out["n_skipped"] == 1
    assert wt.exists()


# ---------------------------------------------------------------------------
# 7. Worktree cleanup prunes merged + old
# ---------------------------------------------------------------------------
def test_worktree_merged_pruned(tmp_path):
    root = _mk_repo(tmp_path)
    wt = root / ".claude" / "worktrees" / "agent-def456"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400.0
    os.utime(wt, (old, old))
    removed: List[str] = []

    def fake_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
        if args[:2] == ["worktree", "list"]:
            return 0, f"worktree {wt.as_posix()}\nbranch refs/heads/merged-x\n\n", ""
        if args[:2] == ["branch", "--merged"]:
            return 0, "* master\n  merged-x\n", ""
        if args[:2] == ["worktree", "remove"]:
            removed.append(args[2])
            return 0, "", ""
        return 1, "", "unknown"
    out = nc.cleanup_worktrees(repo_root=root, age_days=3, commit=True,
                               git_runner=fake_git)
    assert out["n_pruned"] == 1
    assert removed and "agent-def456" in removed[0]


# ---------------------------------------------------------------------------
# 8. --max-age-days override
# ---------------------------------------------------------------------------
def test_max_age_override(tmp_path):
    root = _mk_repo(tmp_path)
    # 10 files at 10 days old — below the default 30d threshold for predictions.
    for i in range(10):
        _touch(root / f"data/cache/predictions_cache_o{i:02d}.parquet",
               days_old=10.0 + i * 0.1, size_kb=1)
    res_default = nc.run_cleanup(root=root, commit=False, include_worktrees=False,
                                 only_category="predictions")
    assert res_default["per_category"]["predictions"]["n_eligible"] == 0
    # Override to 5d → all >5d, but min_keep=7 keeps 7. 10-7 == 3 deletable.
    res_override = nc.run_cleanup(root=root, commit=False, include_worktrees=False,
                                  only_category="predictions", age_override=5)
    assert res_override["per_category"]["predictions"]["n_eligible"] == 3


# ---------------------------------------------------------------------------
# 9. Empty target dir is no-op (no error)
# ---------------------------------------------------------------------------
def test_empty_target_dir_no_op(tmp_path):
    root = _mk_repo(tmp_path)
    # Don't create any files.
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False)
    assert res["total_n_eligible"] == 0
    assert res["total_mb_eligible"] == 0.0
    for cat_info in res["per_category"].values():
        assert cat_info["n_total"] == 0
        assert cat_info["n_eligible"] == 0


# ---------------------------------------------------------------------------
# 10. Permission denied caught as warning + scan continues
# ---------------------------------------------------------------------------
def test_permission_denied_warns(tmp_path, monkeypatch):
    root = _mk_repo(tmp_path)
    # 7 fresh "padding" files protected by min_keep.
    for i in range(7):
        _touch(root / f"data/cache/predictions_cache_pad{i:02d}.parquet",
               days_old=40.0 + i, size_kb=1)
    # 2 ancient ones — both eligible. The "locked" one fails; the other deletes.
    p_locked = _touch(root / "data/cache/predictions_cache_locked.parquet",
                      days_old=200, size_kb=1)
    p_ok = _touch(root / "data/cache/predictions_cache_ok.parquet",
                  days_old=201, size_kb=1)
    real_unlink = Path.unlink
    def fake_unlink(self, *a, **kw):
        if self.name == "predictions_cache_locked.parquet":
            raise PermissionError("locked by another process")
        return real_unlink(self, *a, **kw)
    monkeypatch.setattr(Path, "unlink", fake_unlink)
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    warns = res["per_category"]["predictions"]["warnings"]
    assert any("permission denied" in w for w in warns)
    assert p_locked.exists()  # blocked
    assert not p_ok.exists()  # deleted


# ---------------------------------------------------------------------------
# 11. Symlink not followed (security)
# ---------------------------------------------------------------------------
def test_symlink_not_followed(tmp_path):
    root = _mk_repo(tmp_path)
    real_file = _touch(tmp_path / "outside_real.parquet", days_old=100, size_kb=1)
    link = root / "data/cache/predictions_cache_link.parquet"
    try:
        os.symlink(str(real_file), str(link))
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks not supported on this platform")
    res = nc.run_cleanup(root=root, commit=True, include_worktrees=False,
                         only_category="predictions")
    # Symlink should be classified as 'symlink' reason, not deleted.
    recs = res["per_category"]["predictions"]["records"]
    sym_recs = [r for r in recs if r.get("reason") == "symlink"]
    assert len(sym_recs) == 1
    assert link.is_symlink()  # link still present
    assert real_file.exists()  # target untouched


# ---------------------------------------------------------------------------
# 12. Protected paths never eligible
# ---------------------------------------------------------------------------
def test_protected_paths_never_eligible(tmp_path):
    root = _mk_repo(tmp_path)
    # Inject a custom category that targets protected territory.
    cat = nc.Category("rogue", "data/pnl_ledger.csv", 0, 0)
    _touch(root / "data" / "pnl_ledger.csv", days_old=100, size_kb=1)
    recs = nc.scan_category(cat, root=root, now=time.time())
    assert len(recs) == 1
    assert recs[0]["eligible"] is False
    assert recs[0]["reason"] == "protected"

    # Also protect data/models/* and data/nba/*
    (root / "data" / "models").mkdir(parents=True, exist_ok=True)
    _touch(root / "data" / "models" / "m.parquet", days_old=100, size_kb=1)
    cat2 = nc.Category("rogue2", "data/models/*.parquet", 0, 0)
    recs2 = nc.scan_category(cat2, root=root, now=time.time())
    assert all(r["reason"] == "protected" for r in recs2)


# ---------------------------------------------------------------------------
# 13. --category filter limits scan
# ---------------------------------------------------------------------------
def test_category_filter_limits_scan(tmp_path):
    root = _mk_repo(tmp_path)
    _touch(root / "data/cache/predictions_cache_x.parquet", days_old=100, size_kb=1)
    _touch(root / "data/cache/e2e_smoke_x.json", days_old=100, size_kb=1)
    res = nc.run_cleanup(root=root, commit=False, include_worktrees=False,
                         only_category="e2e")
    assert "e2e" in res["per_category"]
    assert "predictions" not in res["per_category"]


# ---------------------------------------------------------------------------
# 14. CLI happy-path end-to-end via main() returns 0 + JSON
# ---------------------------------------------------------------------------
def test_cli_main_runs_and_emits_json(tmp_path, capsys):
    root = _mk_repo(tmp_path)
    _touch(root / "data/cache/predictions_cache_cli.parquet", days_old=100, size_kb=1)
    rc = nc.main([
        "--root", str(root), "--no-worktrees", "--json",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["commit"] is False
    assert "predictions" in payload["per_category"]
    # JSON output drops the verbose 'records' key.
    assert "records" not in payload["per_category"]["predictions"]


# ---------------------------------------------------------------------------
# 15. Worktree skipped when too fresh
# ---------------------------------------------------------------------------
def test_worktree_fresh_skipped(tmp_path):
    root = _mk_repo(tmp_path)
    wt = root / ".claude" / "worktrees" / "agent-fresh"
    wt.mkdir(parents=True)
    # mtime fresh — should never call git at all (skipped before branch lookup).

    def fake_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
        # branch_map + merged lookup still happen up-front; that's fine.
        if args[:2] == ["worktree", "list"]:
            return 0, "", ""
        if args[:2] == ["branch", "--merged"]:
            return 0, "", ""
        if args[:2] == ["worktree", "remove"]:
            raise AssertionError("fresh worktree should not be removed")
        return 1, "", "unknown"
    out = nc.cleanup_worktrees(repo_root=root, age_days=3, commit=True,
                               git_runner=fake_git)
    assert out["n_pruned"] == 0
    assert any(c["reason"] == "fresh" for c in out["candidates"])
    assert wt.exists()
