"""probe_R20_M5_gamenight_e2e_harness.py — R20_M5 probe.

Runs the game-night E2E harness end-to-end on a real completed historical
game, captures per-stage timings + status, and writes:

    data/cache/probe_R20_M5_results.json

The probe NEVER touches the production pnl_ledger.csv — it routes all
ledger I/O through a dedicated test path (data/pnl_ledger_e2e_test.csv)
and tears it down on the way out.

Exit code 0 only when ALL 5 stages green.
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

SCRIPTS = os.path.join(_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import gamenight_e2e_harness as gn  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache",
                                    "probe_R20_M5_results.json")
TEST_LEDGER = os.path.join(_ROOT, "data", "pnl_ledger_e2e_test.csv")
TEST_BANKROLL = os.path.join(_ROOT, "data", "pnl_bankroll_e2e_test.csv")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    ap = argparse.ArgumentParser(description="R20_M5 game-night E2E harness probe")
    ap.add_argument("--game-id", default=None,
                     help="Override game_id (default auto-pick first complete game)")
    ap.add_argument("--date", default=None,
                     help="Constrain auto-pick to this date YYYY-MM-DD")
    ap.add_argument("--qbox-dir",
                     default=os.path.join(_ROOT, "data", "cache", "quarter_box"))
    args = ap.parse_args()

    t0 = time.time()
    result = gn.run_harness(
        game_id=args.game_id,
        date_str=args.date,
        qbox_dir=args.qbox_dir,
        test_ledger=TEST_LEDGER,
        test_bankroll=TEST_BANKROLL,
    )
    wall_sec = round(time.time() - t0, 3)

    # Compact per-stage view (drop heavy nested payloads).
    per_stage_timing: Dict[str, Any] = {}
    per_stage_status: Dict[str, bool] = {}
    for name, info in (result.get("stage_results") or {}).items():
        per_stage_timing[name] = info.get("runtime_sec")
        per_stage_status[name] = bool(info.get("ok"))

    payload: Dict[str, Any] = {
        "task": "R20_M5 game-night E2E validation harness probe",
        "ts": _iso_now(),
        "status": "SHIP" if result.get("ok") else "REJECT",
        "ok": bool(result.get("ok")),
        "stages_passed": result.get("stages_passed"),
        "n_stages": result.get("n_stages"),
        "game": result.get("game"),
        "runtime_sec_total": result.get("runtime_sec"),
        "wall_runtime_sec": wall_sec,
        "per_stage_status": per_stage_status,
        "per_stage_timing_sec": per_stage_timing,
        "stage_details": result.get("stage_results"),
        "summary": (
            f"all 5 stages green on game "
            f"{(result.get('game') or {}).get('game_id')} "
            f"in {wall_sec}s"
            if result.get("ok") else
            f"FAILED at stage {result.get('stages_passed', 0) + 1}/5; "
            f"see stage_details for reason"
        ),
    }

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    # Always print the headline so loop runners see it in stdout.
    print(json.dumps({
        "status": payload["status"],
        "stages_passed": f"{payload['stages_passed']}/{payload['n_stages']}",
        "game_id": (payload.get("game") or {}).get("game_id"),
        "runtime_sec": payload["wall_runtime_sec"],
        "per_stage_status": payload["per_stage_status"],
        "per_stage_timing_sec": payload["per_stage_timing_sec"],
        "results_path": PROBE_RESULTS_PATH,
    }, indent=2, default=str))

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
