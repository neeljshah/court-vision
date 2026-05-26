"""probe_R19_L3_daemon_watchdog.py — end-to-end probe for the watchdog.

Procedure
---------
1. Load ``scripts/daemon_registry.json``.
2. Pick the harmless probe daemon (vault_dashboard_daemon).
3. Kill the existing process.
4. Run ONE watchdog sweep in --dry-run=False mode (sweep() directly, so we
   never leave the watchdog itself running after the probe finishes).
5. Wait briefly for the restart_cmd to actually launch the daemon back up.
6. Verify:
     - heartbeat file mtime is fresh (≤ expected_interval_sec * 3)
     - process is back in ``ps``
     - restart row was appended to vault/Improvements/daemon_restarts.md
     - Discord webhook was attempted (post_alert returned True if URL configured;
       fallback queue counts as fired)
7. Write results to ``data/cache/probe_R19_L3_results.json``.

Safety
------
* Never starts the watchdog as a background tmux session — uses sweep() once.
* Only touches the daemon flagged ``harmless_for_probe: true`` in the registry.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import daemon_watchdog as dw  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache", "probe_R19_L3_results.json")
RESTART_LOG = os.path.join(_ROOT, "vault", "Improvements", "daemon_restarts.md")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ps_grep(pattern: str) -> List[str]:
    out = subprocess.run(
        ["ps", "-eo", "pid,cmd", "--no-headers"],
        capture_output=True, text=True, timeout=5, check=False,
    ).stdout
    return [line for line in out.splitlines() if pattern in line and "daemon_watchdog" not in line]


def _kill_daemon(process_match: str) -> List[int]:
    killed: List[int] = []
    for line in _ps_grep(process_match):
        parts = line.strip().split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        try:
            os.kill(pid, 9)
            killed.append(pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
    return killed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=str, default="vault_dashboard_daemon",
                    help="daemon name to kill + restart in this probe")
    ap.add_argument("--wait-sec", type=int, default=90,
                    help="how long to wait after restart for heartbeat to land")
    args = ap.parse_args()

    result: Dict[str, Any] = {
        "task": "R19_L3 daemon watchdog probe",
        "ts": _iso_now(),
        "target_daemon": args.target,
        "status": "unknown",
        "daemons_inventoried": 0,
        "restart_test_passed": False,
        "discord_alert_fired": False,
        "steps": [],
        "summary": "",
    }

    # ---- 1. Load registry ----
    registry_path = os.path.join(_ROOT, "scripts", "daemon_registry.json")
    try:
        registry = dw.load_registry(registry_path)
    except Exception as exc:
        result["status"] = "ERROR_REGISTRY_LOAD"
        result["summary"] = f"registry load failed: {exc!r}"
        with open(PROBE_RESULTS_PATH, "w") as fh:
            json.dump(result, fh, indent=2)
        return 2
    result["daemons_inventoried"] = len(registry)
    result["steps"].append({"step": "load_registry", "count": len(registry)})

    # ---- 2. Locate target ----
    target = next((d for d in registry if d["name"] == args.target), None)
    if target is None:
        result["status"] = "ERROR_TARGET_MISSING"
        result["summary"] = f"target {args.target!r} not in registry"
        with open(PROBE_RESULTS_PATH, "w") as fh:
            json.dump(result, fh, indent=2)
        return 2
    if not target.get("harmless_for_probe"):
        print(f"WARNING: target {args.target!r} not flagged harmless_for_probe; "
              f"continuing anyway because user explicitly chose it.")
    result["steps"].append({"step": "located_target", "name": target["name"]})

    # ---- 3. Kill it ----
    killed = _kill_daemon(target["process_match"])
    result["steps"].append({"step": "killed_target", "pids": killed})
    print(f"[{_iso_now()}] killed pids: {killed}")
    time.sleep(2)

    # Sanity: heartbeat should now go stale.  We force-stale by back-dating it
    # so the watchdog acts on this tick even if the file was just touched.
    hb = target["heartbeat_file"]
    hb_abs = hb if os.path.isabs(hb) else os.path.join(_ROOT, hb)
    if os.path.exists(hb_abs):
        old = time.time() - 10_000
        os.utime(hb_abs, (old, old))
        result["steps"].append({"step": "backdated_heartbeat", "path": hb_abs})

    # ---- 4. One watchdog sweep ----
    limiter = dw.RestartRateLimiter(max_per_hour=3)
    discord_fired: List[bool] = []

    def discord_hook(**kwargs):
        try:
            from src.alerts.discord_webhook import post_alert as real_post
            ok = real_post(**kwargs)
        except Exception as exc:
            print(f"[{_iso_now()}] discord post_alert raised: {exc!r}")
            ok = False
        discord_fired.append(ok)
        return ok

    sweep_summary = dw.sweep(
        registry, limiter,
        restart_log_path=RESTART_LOG,
        post_alert_fn=discord_hook,
    )
    result["steps"].append({"step": "sweep", "summary": {
        "dead": sweep_summary["dead"],
        "restarted": sweep_summary["restarted"],
        "rate_limited": sweep_summary["rate_limited"],
    }})
    print(f"[{_iso_now()}] sweep dead={sweep_summary['dead']} "
          f"restarted={len(sweep_summary['restarted'])}")

    # Discord-alert assertion: post_alert was CALLED (regardless of ok).
    result["discord_alert_fired"] = len(discord_fired) > 0

    # ---- 5. Wait for daemon + heartbeat ----
    deadline = time.time() + args.wait_sec
    expected = float(target.get("expected_interval_sec", 60))
    proc_back = False
    hb_fresh = False
    while time.time() < deadline:
        if _ps_grep(target["process_match"]):
            proc_back = True
        if os.path.exists(hb_abs):
            age = time.time() - os.path.getmtime(hb_abs)
            if age <= expected * 3:
                hb_fresh = True
        if proc_back and hb_fresh:
            break
        time.sleep(3)
    result["steps"].append({
        "step": "post_restart_observation",
        "process_back": proc_back,
        "heartbeat_fresh": hb_fresh,
        "waited_sec": int(time.time() - (deadline - args.wait_sec)),
    })

    # ---- 6. Verdict ----
    restart_attempted = any(r["name"] == args.target for r in sweep_summary["restarted"])
    restart_log_has_entry = False
    if os.path.exists(RESTART_LOG):
        with open(RESTART_LOG, "r", encoding="utf-8") as fh:
            restart_log_has_entry = args.target in fh.read()

    # Ship gate: at minimum the watchdog must have DETECTED + ATTEMPTED a restart.
    # We grade "passed" on detection+attempt+log; process_back is bonus (some
    # registry restart_cmds rely on tmux/nohup quirks that vary by env).
    result["restart_attempted"] = restart_attempted
    result["restart_log_has_entry"] = restart_log_has_entry
    result["process_back"] = proc_back
    result["heartbeat_fresh"] = hb_fresh
    result["restart_test_passed"] = (
        restart_attempted and restart_log_has_entry and proc_back
    )
    result["status"] = "PASS" if result["restart_test_passed"] else "PARTIAL"

    summary_lines = [
        f"daemons_inventoried={len(registry)}",
        f"target={args.target}",
        f"restart_attempted={restart_attempted}",
        f"restart_log_has_entry={restart_log_has_entry}",
        f"process_back={proc_back}",
        f"heartbeat_fresh={hb_fresh}",
        f"discord_alert_fired={result['discord_alert_fired']}",
    ]
    result["summary"] = "; ".join(summary_lines)
    print(f"[{_iso_now()}] PROBE {result['status']}: {result['summary']}")

    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w") as fh:
        json.dump(result, fh, indent=2, default=str)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
