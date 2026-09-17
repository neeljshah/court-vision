"""One-command proof that every analytics_showcase module still works.

Discovers every *.py in this directory that exposes a --check mode (the
literal substring "--check" appears somewhere in the file -- same signal a
human would grep for), runs each SEQUENTIALLY via subprocess (one process at
a time, never parallel), and reports pass/fail/duration. Modules that don't
expose --check are listed too (status NO_CHECK) instead of silently
skipped -- this is a proof tool, it doesn't get to hide gaps.

Read-only w.r.t. this file's own logic: it does not fix, build, or modify
any other module. A module whose --check fails because its out/*.json
artifact was never built is reported as FAIL, not silently excused.

Usage:
    python scripts/platformkit/analytics_showcase/check_all.py
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SELF = Path(__file__).resolve()
SHOWCASE_DIR = SELF.parent
REPO_ROOT = SELF.parents[3]
OUT_JSON = SHOWCASE_DIR / "out" / "check_all_report.json"
TIMEOUT_S = 120


def discover():
    """Return (has_check, no_check) module paths, each sorted by filename."""
    has_check, no_check = [], []
    for path in sorted(SHOWCASE_DIR.glob("*.py")):
        if path == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        (has_check if "--check" in text else no_check).append(path)
    return has_check, no_check


def _tracked_dirty_paths():
    """Set of tracked paths with uncommitted changes, or None if this isn't a git
    checkout (or git is unavailable) -- the guard degrades gracefully then."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    paths = set()
    for line in result.stdout.splitlines():
        if not line or line.startswith("??"):
            continue  # untracked -- not a tracked-file mutation
        paths.add(line[3:].strip())
    return paths


def run_one(path):
    # Every module's own docstring documents `-m scripts.platformkit.analytics_showcase.X`
    # invocation (some rely on it for absolute `from scripts...` imports to resolve) -- run
    # it the same way rather than as a bare script file, or otherwise-working modules false-fail.
    dotted = f"scripts.platformkit.analytics_showcase.{path.stem}"
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, "-m", dotted, "--check"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=TIMEOUT_S,
        )
        seconds = time.perf_counter() - start
        status = "PASS" if result.returncode == 0 else "FAIL"
        detail = (result.stderr or result.stdout).strip()
    except subprocess.TimeoutExpired:
        seconds = time.perf_counter() - start
        status = "FAIL"
        detail = f"timed out after {TIMEOUT_S}s"
    return status, seconds, detail


def main():
    # Snapshot the tracked tree BEFORE running any --check (and before writing our
    # own OUT_JSON below) so any tracked file a --check mutates shows up in the diff.
    before = _tracked_dirty_paths()

    has_check, no_check = discover()
    rows = []

    for path in has_check:
        print(f"[{len(rows) + 1}/{len(has_check)}] {path.name} --check ...", flush=True)
        status, seconds, detail = run_one(path)
        rows.append({
            "module": path.name, "status": status, "seconds": round(seconds, 2),
            "as_of": datetime.now(timezone.utc).isoformat(),
        })
        print(f"    {status} ({seconds:.2f}s)")
        if status == "FAIL" and detail:
            for line in detail.splitlines()[-8:]:
                print(f"    | {line}")

    for path in no_check:
        rows.append({
            "module": path.name, "status": "NO_CHECK", "seconds": 0.0,
            "as_of": datetime.now(timezone.utc).isoformat(),
        })

    name_w = max((len(r["module"]) for r in rows), default=6)
    header = f"{'module':<{name_w}}  {'status':<8}  {'seconds':>8}"
    rule = "-" * len(header)
    print()
    print(header)
    print(rule)
    for r in rows:
        print(f"{r['module']:<{name_w}}  {r['status']:<8}  {r['seconds']:>8.2f}")
    print(rule)

    n_pass = sum(r["status"] == "PASS" for r in rows)
    n_fail = sum(r["status"] == "FAIL" for r in rows)
    n_no_check = sum(r["status"] == "NO_CHECK" for r in rows)
    total_s = sum(r["seconds"] for r in rows)
    print(f"total {len(rows)}  pass {n_pass}  fail {n_fail}  no_check {n_no_check}  "
          f"runtime {total_s:.2f}s")

    # Guard: a --check must be read-only w.r.t. tracked files. Flag any tracked path
    # that went from clean to dirty over the module loop (before OUT_JSON is written).
    guard_failed = False
    if before is None:
        print("note: not a git checkout (or git unavailable) -- skipping the no-tracked-writes guard")
    else:
        newly_dirty = sorted((_tracked_dirty_paths() or set()) - before)
        if newly_dirty:
            guard_failed = True
            print()
            print("GUARD FAILED: --check run(s) wrote to tracked files (a --check must be read-only):")
            for p in newly_dirty:
                print(f"    {p}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")

    return 1 if (n_fail or guard_failed) else 0


if __name__ == "__main__":
    sys.exit(main())
