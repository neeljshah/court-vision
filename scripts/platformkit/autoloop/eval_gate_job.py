"""scripts.platformkit.autoloop.eval_gate_job -- M18: cadence-gated REFRESH of
the eval-gate reference-core test scoreboard (data/frontend/ops/
eval_gate_scoreboard_latest.json). eval_gate/run_all.py (docstring: "One-command
proof: run every reference test module and print a consolidated scoreboard")
has no daemon caller and writes no artifact of its own -- a human running it
by hand is the only prior path (measured: run_all.py takes 3.4s wall, 38/38
green, 2026-07-11). This is the daemon side of that gap.

REFRESH ONLY: calls eval_gate.run_all.main(), which itself just imports+runs
every test_*.py module in that package and prints PASS/FAIL counts + exit
code (0 iff all green) -- no verdict math of its own. This job wraps that
call, captures pass/fail per module (not just the exit code), and writes the
one ops-json artifact run_all.py itself never produces.

sys.path SHIM (load-bearing, not invention): run_all.py's own MODULES list
(run_all.py:11-12) is imported via BARE names (`importlib.import_module
("test_eval_core")`, run_all.py:16) -- this only resolves when the eval_gate/
directory itself is on sys.path, which is true when a human runs
`python run_all.py` from inside that dir (script dir auto-prepends) but NOT
true for a package-qualified `from scripts.platformkit.eval_gate import
run_all` (verified: raises ModuleNotFoundError('test_eval_core') without the
shim). _default_run() inserts eval_gate's own directory into sys.path before
calling run_all.main() -- the same effective sys.path a human's `python
run_all.py` invocation gets, nothing more.

argv=[] discipline (the cac9f26f class): run_all.main() takes NO arguments and
never touches sys.argv (verified by read, run_all.py:29) -- there is no argv
to leak here, unlike clv_refresh_job/M16's wrapped CLIs. Documented, not
re-guarded, because there is nothing to guard.

Cadence = eval_gate_scoreboard_latest.json's own mtime. Self-resetting: a
successful run overwrites that file, so the next check needs a fresh 7d
before it fires again -- same convention as M15/M16/M17. Weekly because the
gate is a claims validator (fail-closed regression/leak guard on synthetic
golden fixture), not a live metric that drifts hourly. The `watermarks` dict
param is accepted for call-shape uniformity with every other maintenance job;
unused here.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag. A raise here is isolated by run_all's own
per-job try/except (maintenance_templates._JOB_TABLE), same as every other
job. HONESTY: this job reports PASS/FAIL of the reference-core regression
gate only -- it is never a market-edge or $-ROI claim (see
.claude/rules/no-edge-claims.md).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_eval_gate_job.py -q
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
_EVAL_GATE_DIR = _REPO / "scripts" / "platformkit" / "eval_gate"
_LATEST_PATH = _REPO / "data" / "frontend" / "ops" / "eval_gate_scoreboard_latest.json"
_STALE_AFTER_H = 168.0  # 7d -- claims validator, not a live-drifting metric


def _artifact_age_h(path: Path) -> Optional[float]:
    """Age in hours of the ops-json artifact; None if it does not exist yet
    (treated as due -- there is nothing to be fresh)."""
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _default_run() -> Dict[str, Any]:
    """Run every eval_gate test module via run_all.main() and capture a
    per-module pass/fail scoreboard (not just the bare exit code). sys.path
    shim documented in the module docstring: eval_gate/'s own bare-name
    imports need its directory on sys.path, same as a human's
    `python run_all.py` from inside that dir."""
    eg_dir = str(_EVAL_GATE_DIR)
    added = eg_dir not in sys.path
    if added:
        sys.path.insert(0, eg_dir)
    try:
        from scripts.platformkit.eval_gate import run_all as RA
        rows = []
        total_p = total_n = 0
        for name in RA.MODULES:
            p, n = RA.run_module(name)
            total_p += p
            total_n += n
            rows.append({"module": name, "passed": p, "total": n})
        exit_code = 0 if (total_p == total_n and total_n > 0) else 1
        return {"exit_code": exit_code, "modules": rows,
               "total_passed": total_p, "total_tests": total_n}
    finally:
        if added:
            sys.path.remove(eg_dir)


def _write_ops_json(result: Dict[str, Any], out_path: Path) -> None:
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "honesty_note": "REGRESSION/LEAK GATE ONLY. Not a market or betting edge.",
        "eval_gate_scoreboard": {
            "source_tool": "scripts/platformkit/eval_gate/run_all.py",
            "run_status": "ALL_GREEN" if result["exit_code"] == 0 else "FAILURES_PRESENT",
            "total_passed": result["total_passed"],
            "total_tests": result["total_tests"],
            "modules": result["modules"],
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="ascii")


def run_eval_gate(watermarks: Optional[Dict[str, Any]] = None, *,
                  artifact_path: Optional[Path] = None,
                  age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                  run_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Refresh iff eval_gate_scoreboard_latest.json is >7d stale (or
    missing). Refresh only: reruns the reference-core test scoreboard and
    writes the ops-json artifact run_all.py itself never produces."""
    p = Path(artifact_path) if artifact_path is not None else _LATEST_PATH
    age_h = (age_fn or _artifact_age_h)(p)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    result = (run_fn or _default_run)()
    _write_ops_json(result, p)
    return {"status": "ran", "age_h": age_h, "exit_code": result["exit_code"],
           "total_passed": result["total_passed"], "total_tests": result["total_tests"]}


__all__ = ["run_eval_gate"]
