"""run_pytest_baseline.py -- P0-H-005: the ONE sanctioned overnight full-suite run.

Serial (never xdist), instrumented, budgeted.  The per-file-only pytest rule
exists because an UNINSTRUMENTED full suite froze this box; this runner is the
sanctioned exception that produces the id-aware G1 baseline.

Produces (all under .planning/platform/baselines/, gitignored):
  pytest_baseline.txt        id-aware JSON: counts + frozen failing/error ids
  pytest_durations.txt       slowlist from --durations=0 (slowest first)
  pytest_baseline_junit.xml  raw junit-xml of the run
  pytest_capture_stdout.txt  full pytest stdout (durations feedstock)
  pytest_mutators.md         written by the CV_HERMETIC_TRACE conftest hook

Launch detached (git-bash):
  cd /c/Users/neelj/nba-ai-system && nohup \
    /c/Users/neelj/anaconda3/envs/basketball_ai/python \
    scripts/platformkit/run_pytest_baseline.py \
    > logs/pytest_baseline_capture.log 2>&1 &

Windows caveat (documented, accepted): --timeout-method=thread cannot
interrupt a hung C extension; the 8h total budget is the backstop.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))
from capture_pytest_baseline import parse_durations, parse_junit_xml  # noqa: E402

BASELINES = ROOT / ".planning" / "platform" / "baselines"
BUDGET_S = int(os.environ.get("CV_BASELINE_BUDGET_S", "28800"))  # 8h hard stop
PER_TEST_TIMEOUT = "300"
STOP_WINDOW = ROOT / "scripts" / "platform_harness" / "stop_window.py"


def _say(msg: str) -> None:
    print("[baseline] " + msg, flush=True)


def _below_normal_priority() -> bool:
    """Lower our priority; the pytest child inherits it. LIVE-SYSTEM CARE."""
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        return True
    except Exception:
        return False


def _stop_window(action: str) -> bool:
    """Open/close the loop STOP window via the sanctioned harness tool."""
    try:
        r = subprocess.run(
            [sys.executable, str(STOP_WINDOW), "--" + action, "P0-H-005",
             "--execute"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        _say("stop_window --%s rc=%d" % (action, r.returncode))
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        _say("stop_window --%s failed: %s" % (action, e))
        return False


def main() -> int:
    BASELINES.mkdir(parents=True, exist_ok=True)
    junit = BASELINES / "pytest_baseline_junit.xml"
    stdout_txt = BASELINES / "pytest_capture_stdout.txt"

    _say("P0-H-005 capture start %s budget=%ds"
         % (dt.datetime.now().isoformat(timespec="seconds"), BUDGET_S))
    _say("below-normal priority: %s" % _below_normal_priority())

    # CV_BASELINE_TARGET: smoke-test override only; the real capture uses tests/.
    target = os.environ.get("CV_BASELINE_TARGET", str(ROOT / "tests"))
    cmd = [sys.executable, "-m", "pytest", target, "-q",
           "--timeout=" + PER_TEST_TIMEOUT, "--timeout-method=thread",
           "--durations=0", "--junitxml=" + str(junit)]
    env = {**os.environ, "NBA_OFFLINE": "1", "CV_HERMETIC_TRACE": "1"}

    _stop_window("open")
    t0 = time.monotonic()
    timed_out, rc = False, None
    try:
        with stdout_txt.open("w", encoding="utf-8", errors="replace") as fh:
            try:
                r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                   cwd=str(ROOT), env=env, timeout=BUDGET_S)
                rc = r.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        _stop_window("close")
    elapsed = time.monotonic() - t0
    _say("pytest done rc=%s timed_out=%s elapsed=%.0fs" % (rc, timed_out, elapsed))

    parsed = None
    if junit.exists():
        try:
            parsed = parse_junit_xml(junit)
        except Exception as e:  # noqa: BLE001
            _say("junit parse failed: %s" % e)
    partial = timed_out or parsed is None

    baseline = {
        "captured_at": dt.datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "budget_s": BUDGET_S,
        "rc": rc,
        "timed_out": timed_out,
        "partial": partial,
        "note": ("PARTIAL BASELINE -- budget exceeded or junit missing; "
                 "NOT valid for G1") if partial else
                "full-suite serial baseline (P0-H-005)",
        "passed": parsed["passed"] if parsed else None,
        "skipped": parsed["skipped"] if parsed else None,
        "total_collected": parsed["total_collected"] if parsed else None,
        "failed_ids": sorted(parsed["failed_ids"]) if parsed else [],
        "error_ids": sorted(parsed["error_ids"]) if parsed else [],
    }
    (BASELINES / "pytest_baseline.txt").write_text(
        json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    _say("wrote pytest_baseline.txt (partial=%s)" % partial)

    try:
        durs = parse_durations(stdout_txt.read_text(encoding="utf-8",
                                                    errors="replace"))
        with (BASELINES / "pytest_durations.txt").open("w", encoding="utf-8") as fh:
            for nodeid, secs in durs:
                fh.write("%10.2fs %s\n" % (secs, nodeid))
        _say("wrote pytest_durations.txt (%d entries)" % len(durs))
    except Exception as e:  # noqa: BLE001
        _say("durations parse failed: %s" % e)

    mut = BASELINES / "pytest_mutators.md"
    if not mut.exists():
        mut.write_text("# pytest mutators (CV_HERMETIC_TRACE capture run)\n\n"
                       "(hook produced no file -- run did not reach "
                       "sessionstart)\n", encoding="utf-8")

    try:
        import harness_state
        harness_state.append_ledger(
            "pytest_baseline_capture", elapsed_s=round(elapsed, 1), rc=rc,
            timed_out=timed_out, partial=partial,
            collected=baseline["total_collected"],
            failed=len(baseline["failed_ids"]),
            errors=len(baseline["error_ids"]))
    except Exception as e:  # noqa: BLE001
        _say("ledger append failed: %s" % e)

    _say("capture %s: collected=%s failed=%d errors=%d"
         % ("PARTIAL" if partial else "COMPLETE",
            baseline["total_collected"], len(baseline["failed_ids"]),
            len(baseline["error_ids"])))
    return 3 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
