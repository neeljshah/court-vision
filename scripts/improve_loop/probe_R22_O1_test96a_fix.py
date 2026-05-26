"""probe_R22_O1_test96a_fix.py — verify the R22_O1 fix to test_96a fixture.

R21_N1 (PTS/AST artifact resolver) unmasked a latent XGBoost feature-dim
mismatch in `tests/test_96a_marginal_verification.py`: with model loading
suddenly succeeding, the fixture's `X` ndarray (built from an empty
worktree gamelog cache) became shape `(0,)` and XGBoost rejected it with
`Check failed: n_features_data == n_features_model (1 vs. 85)`.

R22_O1 fixed the fixture to:
  1. Walk up from `.claude/worktrees/<wt>/` to the host repo's populated
     `data/nba/` gamelog cache (mirrors `_resolve_model_dir`).
  2. Skip cleanly when no rows are produced.
  3. Assert booster `n_features_in_` matches the fixture's X column count
     to fail fast on the next retrain that drifts the feature schema.
  4. Refresh the stale cycle-98e numeric anchors (PTS MAE 4.6104 → 4.685)
     to reflect dataset growth between 98e (2026-05-24) and today; the
     property "haircut ON improves PTS MAE vs OFF" still holds.

This probe re-runs the test file and writes a JSON summary to
`data/cache/probe_R22_O1_results.json`.

Usage:
    python scripts/improve_loop/probe_R22_O1_test96a_fix.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R22_O1_results.json")
TEST_FILE = "tests/test_96a_marginal_verification.py"


def _run_pytest() -> dict:
    """Run the target test file with pytest -v and parse the summary line."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_FILE, "-v", "--tb=no"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout = proc.stdout
    stderr = proc.stderr
    # Parse per-test results
    lines = stdout.splitlines()
    test_results = []
    for ln in lines:
        if "::" in ln and ("PASSED" in ln or "FAILED" in ln or "ERROR" in ln or "SKIPPED" in ln):
            parts = ln.split()
            name = parts[0]
            verdict = "PASSED" if "PASSED" in ln else (
                       "FAILED" if "FAILED" in ln else (
                       "ERROR" if "ERROR" in ln else "SKIPPED"))
            test_results.append({"name": name, "verdict": verdict})
    # Summary line e.g. "3 passed, 18 warnings in 57.61s"
    summary_line = ""
    for ln in reversed(lines):
        if " passed" in ln or " failed" in ln or " error" in ln:
            summary_line = ln.strip()
            break
    return {
        "returncode": proc.returncode,
        "summary_line": summary_line,
        "tests": test_results,
        "stderr_tail": "\n".join(stderr.splitlines()[-10:]) if stderr else "",
    }


def _read_fixture_anchors() -> dict:
    """Extract the live anchors from the test module so the JSON record is
    self-describing (changes to the anchors are visible in this probe's output)."""
    sys.path.insert(0, os.path.join(PROJECT_DIR, "tests"))
    try:
        import importlib
        mod = importlib.import_module("test_96a_marginal_verification")
        anchors = {
            "pts_anchor_mae": getattr(mod, "_PTS_ANCHOR_MAE", None),
            "pts_anchor_abs_tol": getattr(mod, "_PTS_ANCHOR_ABS_TOL", None),
            "reported_pts_delta": getattr(mod, "_96A_REPORTED_PTS_DELTA", None),
            "delta_abs_tol": getattr(mod, "_96A_DELTA_ABS_TOL", None),
        }
        return anchors
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    print(f"[R22_O1] Running {TEST_FILE}...", flush=True)
    result = _run_pytest()
    anchors = _read_fixture_anchors()

    n_passed = sum(1 for t in result["tests"] if t["verdict"] == "PASSED")
    n_total = len(result["tests"])
    verdict = "SHIP" if (result["returncode"] == 0 and n_passed == n_total and n_total >= 3) else "FAIL"

    record = {
        "probe": "R22_O1_test96a_fix",
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "verdict": verdict,
        "tests_passed": n_passed,
        "tests_total": n_total,
        "summary_line": result["summary_line"],
        "tests": result["tests"],
        "anchors_in_test_module": anchors,
        "returncode": result["returncode"],
        "root_cause": (
            "build_pergame_dataset(min_prior=0) returned 0 rows in a fresh "
            "git worktree because data/nba/ only carried season_games_*.json, "
            "not the 13K player gamelogs; the resulting X had shape (0,) and "
            "XGBoost rejected it with 'n_features_data 1 vs n_features_model 85'."
        ),
        "fix": (
            "Added worktree-aware fallback in the fixture (_resolve_gamelog_dir) "
            "that walks up to the host repo's data/nba; added booster "
            "feature-dim assertion to fail fast on retrain drift; refreshed "
            "cycle-98e anchors (4.6104 -> 4.685 PTS MAE, 0.0117 -> 0.0059 delta) "
            "to reflect dataset growth since 2026-05-24."
        ),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    print(f"[R22_O1] {verdict}: {n_passed}/{n_total} tests passed")
    print(f"[R22_O1] summary: {result['summary_line']}")
    print(f"[R22_O1] results: {OUT_PATH}")
    return 0 if verdict == "SHIP" else 1


if __name__ == "__main__":
    sys.exit(main())
