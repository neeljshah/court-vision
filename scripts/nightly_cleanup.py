"""nightly_cleanup.py — R28_U3 nightly disk cleanup orchestrator.

Per-category prune of caches/snapshots/heartbeats/probes/lines + stale
worktrees. Dry-run by default; --commit to actually delete.

NEVER deletes: data/pnl_ledger.csv, data/models/*, data/nba/*, data/backups/*
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

PROTECTED_PREFIXES: Tuple[str, ...] = (
    "data/pnl_ledger.csv",
    "data/models/",
    "data/nba/",
    "data/backups/",
)


def _is_protected(path: Path, root: Path) -> bool:
    """True if `path` lies under any PROTECTED_PREFIXES (or IS one)."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return True
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in PROTECTED_PREFIXES)


@dataclass
class Category:
    name:         str
    glob_pattern: str
    age_days:     int
    min_keep:     int = 7
    recursive:    bool = False


DEFAULT_CATEGORIES: Tuple[Category, ...] = (
    Category("predictions", "data/cache/predictions_cache_*.parquet", 30, 7),
    Category("injuries",    "data/cache/nba_injuries_*.parquet",      30, 7),
    Category("alerts",      "data/cache/alerts/critical_*.json",      14, 7),
    Category("e2e",         "data/cache/e2e_smoke_*.json",            14, 7),
    Category("heartbeats",  "data/cache/daemon_heartbeats/*.txt",      7, 0),
    Category("snapshots",   "data/cache/rec_tracker/rec_snapshot_*.json", 60, 14),
    Category("probes",      "data/cache/probe_R*_results.json",       30, 14),
    Category("m2",          "data/cache/m2_family_predictions_*.json", 30, 7),
    Category("lines",       "data/lines/snapshots/*.csv",             30, 14),
)


def _age_days(path: Path, now: float) -> float:
    try:
        return (now - path.stat().st_mtime) / 86400.0
    except OSError:
        return -1.0


def _size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / 1024.0 / 1024.0
    except OSError:
        return 0.0


def scan_category(
    cat: Category, *, root: Path, now: float,
    age_override: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Records [{path, age_days, size_mb, eligible, reason}, ...] for one cat.

    `eligible=True` ⇔ file would be deleted on --commit. min_keep preserves
    the youngest N. Protected paths + symlinks NEVER eligible.
    """
    threshold = int(age_override if age_override is not None else cat.age_days)
    try:
        raw = list(root.rglob(cat.glob_pattern) if cat.recursive
                   else root.glob(cat.glob_pattern))
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for p in raw:
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        if p.is_symlink():
            out.append({"path": str(p), "age_days": 0.0, "size_mb": 0.0,
                        "eligible": False, "reason": "symlink"})
            continue
        if _is_protected(p, root):
            out.append({"path": str(p), "age_days": 0.0, "size_mb": 0.0,
                        "eligible": False, "reason": "protected"})
            continue
        age = _age_days(p, now)
        out.append({"path": str(p), "age_days": age, "size_mb": _size_mb(p),
                    "eligible": age > threshold, "reason": ""})
    keep_n = max(0, int(cat.min_keep))
    if keep_n > 0:
        live = [r for r in out if r["reason"] == ""]
        live.sort(key=lambda r: r["age_days"])
        for r in live[:keep_n]:
            if r["eligible"]:
                r["eligible"] = False
                r["reason"] = "min_keep"
    return out


def apply_deletions(
    records: List[Dict[str, Any]], *, commit: bool,
) -> Tuple[int, float, List[str]]:
    """Delete `eligible=True` iff `commit`. Returns (n, mb_freed, warnings)."""
    n = 0
    mb = 0.0
    warns: List[str] = []
    for r in records:
        if not r.get("eligible"):
            continue
        if not commit:
            n += 1
            mb += float(r.get("size_mb", 0.0))
            continue
        p = Path(r["path"])
        try:
            size_before = _size_mb(p)
            p.unlink()
            n += 1
            mb += size_before
            r["deleted"] = True
        except PermissionError as exc:
            warns.append(f"permission denied: {p} — {exc!r}")
        except OSError as exc:
            warns.append(f"unlink failed: {p} — {exc!r}")
    return n, mb, warns


# ---- worktree pruning ------------------------------------------------------ #
def _git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd),
                              capture_output=True, text=True, timeout=20)
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return 1, "", repr(exc)


def _worktree_branch_map(
    repo_root: Path,
    runner: Callable[[List[str], Path], Tuple[int, str, str]] = _git,
) -> Dict[str, str]:
    """Parse `git worktree list --porcelain` into {worktree_path: branch}."""
    code, out, _ = runner(["worktree", "list", "--porcelain"], repo_root)
    mp: Dict[str, str] = {}
    if code != 0:
        return mp
    cur = ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = line.split(" ", 1)[1].strip()
            mp[cur] = ""
        elif line.startswith("branch ") and cur:
            mp[cur] = line.split(" ", 1)[1].replace("refs/heads/", "").strip()
    return mp


def _merged_branches(
    repo_root: Path,
    runner: Callable[[List[str], Path], Tuple[int, str, str]] = _git,
) -> set:
    code, out, _ = runner(["branch", "--merged", "master"], repo_root)
    if code != 0:
        return set()
    return {ln.strip().lstrip("* ").strip() for ln in out.splitlines() if ln.strip()}


def cleanup_worktrees(
    *, repo_root: Path, age_days: int = 3, commit: bool = False,
    git_runner: Optional[Callable[[List[str], Path], Tuple[int, str, str]]] = None,
) -> Dict[str, Any]:
    """Prune `.claude/worktrees/agent-*` mtime>age_days AND merged-into-master."""
    runner = git_runner or _git
    wt_dir = repo_root / ".claude" / "worktrees"
    if not wt_dir.is_dir():
        return {"candidates": [], "n_pruned": 0, "n_skipped": 0, "warnings": []}
    now = time.time()
    branch_map = _worktree_branch_map(repo_root, runner)
    merged = _merged_branches(repo_root, runner)
    cands: List[Dict[str, Any]] = []
    warns: List[str] = []
    n_pruned = n_skipped = 0
    for entry in sorted(wt_dir.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("agent-"):
            continue
        try:
            age = (now - entry.stat().st_mtime) / 86400.0
        except OSError:
            continue
        if age <= age_days:
            cands.append({"path": str(entry), "age_days": age,
                          "pruned": False, "reason": "fresh"})
            continue
        # Match by suffix — porcelain paths use forward slashes.
        branch = ""
        for wt_path, br in branch_map.items():
            if wt_path.endswith(entry.name):
                branch = br
                break
        if not branch or branch not in merged:
            n_skipped += 1
            cands.append({"path": str(entry), "age_days": age, "branch": branch,
                          "pruned": False, "reason": "not_merged"})
            continue
        if not commit:
            n_pruned += 1
            cands.append({"path": str(entry), "age_days": age, "branch": branch,
                          "pruned": False, "reason": "dry_run"})
            continue
        code, _, err = runner(["worktree", "remove", str(entry)], repo_root)
        if code == 0:
            n_pruned += 1
            cands.append({"path": str(entry), "age_days": age, "branch": branch,
                          "pruned": True, "reason": "removed"})
        else:
            warns.append(f"worktree remove failed: {entry.name} — {err.strip()[:80]}")
            cands.append({"path": str(entry), "age_days": age, "branch": branch,
                          "pruned": False, "reason": f"git_err"})
    return {"candidates": cands, "n_pruned": n_pruned,
            "n_skipped": n_skipped, "warnings": warns}


def _archive_probes_category(
    *, root: Path, commit: bool, age_override: Optional[int],
) -> Dict[str, Any]:
    """R31_X4 integration — archive (not delete) probe results.

    Imports lazily so the rest of nightly_cleanup remains importable even
    if the archiver module is renamed or moved.
    """
    try:
        from scripts import archive_probe_results as apr  # noqa: WPS433
    except ImportError as exc:
        return {
            "n_eligible":  0,
            "mb_eligible": 0.0,
            "n_total":     0,
            "glob_pattern": "data/cache/probe_R*_results.json",
            "age_days":    int(age_override or apr_default_keep()),
            "min_keep":    0,
            "warnings":    [f"archive_probe_results import failed: {exc!r}"],
            "records":     [],
        }
    keep_days = int(age_override if age_override is not None
                    else apr.DEFAULT_KEEP_DAYS)
    res = apr.archive_probes(
        root=root, keep_days=keep_days,
        min_keep=apr.DEFAULT_MIN_KEEP, commit=commit,
    )
    return {
        "n_eligible":   int(res.get("n_eligible", 0) or 0),
        "mb_eligible":  float(res.get("size_mb_estimate", 0.0) or 0.0),
        "n_total":      int(res.get("n_eligible", 0) or 0),
        "glob_pattern": "data/cache/probe_R*_results.json",
        "age_days":     keep_days,
        "min_keep":     apr.DEFAULT_MIN_KEEP,
        "warnings":     list(res.get("warnings", []) or []),
        "archive":      res.get("archive"),
        "n_archived":   int(res.get("n_archived", 0) or 0),
        "n_deleted":    int(res.get("n_deleted", 0) or 0),
        "records":      [],
    }


def apr_default_keep() -> int:
    """Fallback default if the archiver module fails to import."""
    return 7


def run_cleanup(
    *, root: Path,
    categories: Tuple[Category, ...] = DEFAULT_CATEGORIES,
    commit: bool = False,
    only_category: Optional[str] = None,
    age_override: Optional[int] = None,
    include_worktrees: bool = True,
    worktree_age_days: int = 3,
    include_archive_probes: bool = True,
) -> Dict[str, Any]:
    """Run every category. Returns a result dict (never raises).

    The legacy ``probes`` category (delete-on-age) is still listed but
    is best left at age_days=30 so the new ``archive_probes`` category
    catches the in-between window (7-30d) and preserves history.
    """
    now = time.time()
    per_cat: Dict[str, Dict[str, Any]] = {}
    total_n = 0
    total_mb = 0.0
    all_warns: List[str] = []
    for cat in categories:
        if only_category and cat.name != only_category:
            continue
        recs = scan_category(cat, root=root, now=now, age_override=age_override)
        n, mb, warns = apply_deletions(recs, commit=commit)
        per_cat[cat.name] = {
            "n_eligible":   n,
            "mb_eligible":  round(mb, 4),
            "n_total":      len(recs),
            "glob_pattern": cat.glob_pattern,
            "age_days":     int(age_override if age_override is not None else cat.age_days),
            "min_keep":     cat.min_keep,
            "warnings":     warns,
            "records":      recs,
        }
        total_n += n
        total_mb += mb
        all_warns.extend(warns)
    if include_archive_probes and (
        only_category is None or only_category == "archive_probes"
    ):
        ap_info = _archive_probes_category(
            root=root, commit=commit, age_override=age_override,
        )
        per_cat["archive_probes"] = ap_info
        total_n += int(ap_info.get("n_eligible", 0) or 0)
        total_mb += float(ap_info.get("mb_eligible", 0.0) or 0.0)
        all_warns.extend(ap_info.get("warnings", []) or [])
    wt: Dict[str, Any] = {}
    if include_worktrees and (only_category is None or only_category == "worktrees"):
        wt = cleanup_worktrees(repo_root=root, age_days=worktree_age_days, commit=commit)
        all_warns.extend(wt.get("warnings", []))
    return {
        "root":              str(root),
        "commit":            bool(commit),
        "total_n_eligible":  total_n,
        "total_mb_eligible": round(total_mb, 4),
        "per_category":      per_cat,
        "worktrees":         wt,
        "warnings":          all_warns,
    }


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="R28_U3 nightly cleanup (dry-run by default).")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--category", type=str, default=None)
    ap.add_argument("--max-age-days", type=int, default=None)
    ap.add_argument("--no-worktrees", action="store_true")
    ap.add_argument("--no-archive-probes", action="store_true",
                    help="skip R31_X4 probe-results archiver step")
    ap.add_argument("--worktree-age-days", type=int, default=3)
    ap.add_argument("--root", type=str, default=_ROOT)
    ap.add_argument("--json", action="store_true")
    return ap.parse_args(argv)


def _print_result(result: Dict[str, Any]) -> None:
    mode = "COMMIT" if result.get("commit") else "DRY-RUN"
    print(f"[{mode}] total_eligible={result.get('total_n_eligible', 0)} "
          f"mb={result.get('total_mb_eligible', 0.0):.2f}")
    for name, info in result.get("per_category", {}).items():
        print(f"  {name:<12} n={info['n_eligible']:>4} mb={info['mb_eligible']:>8.2f}  "
              f"(matched={info['n_total']:>4}, age>{info['age_days']}d, "
              f"min_keep={info['min_keep']})")
    wt = result.get("worktrees", {}) or {}
    if wt:
        print(f"  worktrees    n_pruned={wt.get('n_pruned', 0)} "
              f"n_skipped={wt.get('n_skipped', 0)}")
    for w in result.get("warnings", [])[:5]:
        print(f"  WARN: {w}")


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    result = run_cleanup(
        root=Path(args.root),
        commit=bool(args.commit),
        only_category=args.category,
        age_override=args.max_age_days,
        include_worktrees=not args.no_worktrees,
        worktree_age_days=int(args.worktree_age_days),
        include_archive_probes=not args.no_archive_probes,
    )
    if args.json:
        slim = json.loads(json.dumps(result, default=str))
        for v in slim.get("per_category", {}).values():
            v.pop("records", None)
        print(json.dumps(slim, indent=2, default=str))
    else:
        _print_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
