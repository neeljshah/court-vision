"""probe_R27_T5_e2e_smoke.py — R27_T5 probe.

Runs scripts/e2e_smoke_test.run_smoke end-to-end, captures the per-stage
pass/fail distribution, and writes a compact results JSON to:

    data/cache/probe_R27_T5_results.json

The probe reports n_passed / n_failed / n_skipped / n_timeout and exits
non-zero iff any stage FAILED or TIMED OUT. Stages that SKIP (data
unavailable in this environment) are not counted as failures — only
hard breakage is.

Exit code:
    0  iff ship-gate met (>= SHIP_GATE_MIN_PASSES PASS AND no FAIL/TIMEOUT)
    1  otherwise
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import e2e_smoke_test as smoke  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache", "probe_R27_T5_results.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    ap = argparse.ArgumentParser(description="R27_T5 e2e smoke probe")
    ap.add_argument("--json-out", default=None,
                    help="Optional secondary JSON output path")
    args = ap.parse_args()

    t0 = time.time()
    summary = smoke.run_smoke(quiet=True)
    wall = round(time.time() - t0, 3)

    n_passed = int(summary.get("n_passed", 0))
    n_failed = int(summary.get("n_failed", 0))
    n_skipped = int(summary.get("n_skipped", 0))
    n_timeout = int(summary.get("n_timeout", 0))

    # Probe-level ship gate: at least SHIP_GATE_MIN_PASSES PASS,
    # AND no FAIL/TIMEOUT, AND runtime under cap.
    ship_gate_met = (
        n_passed >= smoke.SHIP_GATE_MIN_PASSES
        and n_failed == 0
        and n_timeout == 0
        and float(summary.get("runtime_sec", 0)) <= smoke.OVERALL_TIMEOUT_SEC
    )
    status = "SHIP" if ship_gate_met else "REJECT"

    per_stage_status: Dict[str, str] = {
        s["name"]: s["status"] for s in summary.get("stages", [])
    }
    per_stage_timing: Dict[str, float] = {
        s["name"]: float(s.get("runtime_sec", 0.0)) for s in summary.get("stages", [])
    }

    payload: Dict[str, Any] = {
        "task": "R27_T5 end-to-end smoke probe",
        "ts": _iso_now(),
        "status": status,
        "ok": ship_gate_met,
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_skipped": n_skipped,
        "n_timeout": n_timeout,
        "n_stages": int(summary.get("n_stages", 0)),
        "ship_gate_min_passes": smoke.SHIP_GATE_MIN_PASSES,
        "runtime_sec": float(summary.get("runtime_sec", 0.0)),
        "wall_runtime_sec": wall,
        "overall_cap_sec": smoke.OVERALL_TIMEOUT_SEC,
        "failed_stage_names": list(summary.get("failed_stage_names") or []),
        "per_stage_status": per_stage_status,
        "per_stage_timing_sec": per_stage_timing,
        "summary": (
            f"{n_passed}/{summary.get('n_stages')} PASS, "
            f"{n_failed} FAIL, {n_skipped} SKIP, {n_timeout} TIMEOUT "
            f"in {summary.get('runtime_sec')}s"
        ),
        "smoke_results_path": summary.get("results_path"),
    }

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)

    # Always print the headline JSON so loop runners see it.
    print(json.dumps({
        "status": payload["status"],
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_skipped": n_skipped,
        "n_timeout": n_timeout,
        "runtime_sec": payload["runtime_sec"],
        "failed_stage_names": payload["failed_stage_names"],
        "results_path": PROBE_RESULTS_PATH,
    }, indent=2, default=str))

    return 0 if ship_gate_met else 1


if __name__ == "__main__":
    sys.exit(main())
