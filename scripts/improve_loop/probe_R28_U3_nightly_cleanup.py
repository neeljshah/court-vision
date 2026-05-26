"""probe_R28_U3_nightly_cleanup.py — dry-run inventory probe for R28_U3.

Runs ``nightly_cleanup.run_cleanup(commit=False)`` against the real
``data/cache/`` (LOCAL ONLY — no SSH/RunPod). Reports counts + MB per
category. Persists results to ``data/cache/probe_R28_U3_results.json``.

Hard rules
----------
* Never calls --commit. Never deletes anything.
* Never touches data/pnl_ledger.csv, data/models, data/nba, data/backups
  (the cleanup script's own allowlist blocks them, but the probe does
  --dry-run regardless).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import nightly_cleanup as nc  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R28_U3_results.json"
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "probe":      "R28_U3",
        "started_at": _iso_now(),
    }
    try:
        # Probe against the canonical repo root (one level up from this
        # worktree if we're inside .claude/worktrees, else the worktree
        # itself).
        candidate = Path(_ROOT)
        # If we're inside a worktree, prefer the main repo root so the
        # inventory reflects the maintainer's actual disk pressure.
        # Heuristic: if our path matches ``.claude/worktrees/agent-*``
        # then walk up 3 levels.
        parts = candidate.as_posix().split("/")
        if len(parts) >= 4 and parts[-3:-1] == [".claude", "worktrees"]:
            candidate = candidate.parents[2]
        # Final guard — must exist + contain data/cache.
        if not (candidate / "data" / "cache").is_dir():
            candidate = Path(_ROOT)
        out["scan_root"] = str(candidate)

        result = nc.run_cleanup(
            root=candidate, commit=False,
            include_worktrees=True, worktree_age_days=3,
        )
        # Slim records out of the persisted payload — keep totals.
        slim_per_cat: Dict[str, Dict[str, Any]] = {}
        for name, info in (result.get("per_category") or {}).items():
            slim_per_cat[name] = {
                "n_eligible":   info.get("n_eligible", 0),
                "n_total":      info.get("n_total", 0),
                "mb_eligible":  info.get("mb_eligible", 0.0),
                "age_days":     info.get("age_days", 0),
                "min_keep":     info.get("min_keep", 0),
                "glob_pattern": info.get("glob_pattern", ""),
            }
        wt = result.get("worktrees", {}) or {}
        out["per_category"]      = slim_per_cat
        out["total_n_eligible"]  = int(result.get("total_n_eligible", 0) or 0)
        out["total_mb_eligible"] = float(result.get("total_mb_eligible", 0.0) or 0.0)
        out["worktrees"] = {
            "n_pruned_dry":  int(wt.get("n_pruned", 0) or 0),
            "n_skipped":     int(wt.get("n_skipped", 0) or 0),
            "n_candidates":  len(wt.get("candidates", []) or []),
        }
        out["n_warnings"] = len(result.get("warnings", []) or [])
        out["ship_ok"] = True
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = repr(exc)
        out["ship_ok"] = False
    out["ended_at"] = _iso_now()
    return out


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe":     "R28_U3",
            "timestamp": _iso_now(),
            "ship_ok":   False,
            "error":     repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ship_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
