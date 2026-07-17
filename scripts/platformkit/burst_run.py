"""scripts.platformkit.burst_run -- the ON-DEMAND BURST RUNNER.

The resident 48-proc fleet is paused (15.5GB RAM, upgrade pending), so the same
maintenance work now runs as a ONE-SHOT, single-process burst instead of a
standing daemon set. This mirrors autoloop.maintenance_templates.run_all()'s
dispatch shape: a step table, each entry imported + called fresh, every step
exception-isolated so one failure never sinks the burst.

Each step reuses an EXISTING single-tick callable (never reimplemented):
  1. line_snapshot    line_snapshot_daemon.poll_once per active sport      (slow, network)
  2. settle_sweep     settle_sweep_daemon.tick + grade_predictions.grade_predictions (slow, ESPN)
  3. pnl_bestbets     pnl_series.build_and_write + bestbets_compute_runner.tick
  4. analytics_verify analytics_verify.cycle.run_cycle
  5. feed_health      feed_health_runner.tick                              (slow, network)
  6. freshness_sla    freshness_sla_runner.tick

Steps marked slow (network) are skipped under --skip-slow. Per step we log wall
time + RSS delta (ctypes GetProcessMemoryInfo) and record it in a burst report.
Hard RSS guard: cross 3GB and the remaining steps are skipped (aborted_reason).

CLI: python -m scripts.platformkit.burst_run [--steps a,b,c] [--skip-slow]

No live in-game capture, no real-time CLV -- those are daemon-loop-only and are
NOT run in burst mode (see docs/research/ondemand_mode_2026_07_16.md). UNITS
only; no $/edge is ever claimed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
REPORT_PATH = _REPO / "data" / "cache" / "analytics_verify" / "burst_report.json"
RSS_LIMIT_MB = 3072.0  # 3GB hard guard
_HONEST_NOTE = (
    "On-demand burst: single process, sequential exception-isolated steps. NOT "
    "run in burst mode: live in-game capture + real-time CLV ticks (daemon-loop "
    "only). UNITS only; no $/edge claimed.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rss_mb() -> float:
    """Current process working-set (RSS) in MB via GetProcessMemoryInfo.
    Returns 0.0 where unavailable (non-Windows / API failure) -- never raises."""
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # argtypes/restype are REQUIRED on 64-bit: without them ctypes truncates
        # the HANDLE to a c_int and the call silently fails (returns 0, ws=0).
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = _PMC()
        counters.cb = ctypes.sizeof(_PMC)
        h = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb)
        if ok:
            return counters.WorkingSetSize / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001 -- diagnostics only; never sink a step
        pass
    return 0.0


# --- step callables: each imports fresh + reuses an existing single-tick fn ---
def _step_line_snapshot() -> Dict[str, Any]:
    from scripts.platformkit.odds_provider.line_snapshot_daemon import (
        DEFAULT_SPORTS, poll_once)
    reps = [poll_once(s) for s in DEFAULT_SPORTS]  # poll_once never raises per sport
    return {"sports": len(reps),
            "logged": sum(int(r.get("logged", 0)) for r in reps)}


def _step_settle_sweep() -> Dict[str, Any]:
    from scripts.platformkit.paper.grade_predictions import grade_predictions
    from scripts.platformkit.paper.settle_sweep_daemon import tick as settle_tick
    settle = settle_tick(now=time.time())
    grade = grade_predictions()
    return {"settle": settle, "graded_now": grade.get("n_graded_now")}


def _step_pnl_bestbets() -> Dict[str, Any]:
    from scripts.platformkit.bestbets.bestbets_compute_runner import tick as bb_tick
    from scripts.platformkit.paper.pnl_series import build_and_write
    pnl = build_and_write()
    bb = bb_tick(now=time.time())
    return {"pnl_days": len((pnl or {}).get("per_day", [])),
            "bestbets_cards": len((bb or {}).get("cards", []))}


def _step_analytics_verify() -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify.cycle import run_cycle
    return run_cycle() or {}


def _step_feed_health() -> Dict[str, Any]:
    from scripts.platformkit.odds_provider.feed_health_runner import tick
    doc = tick(now=time.time()) or {}
    return {"overall": doc.get("overall"), "n_red": doc.get("n_red")}


def _step_freshness_sla() -> Dict[str, Any]:
    from scripts.platformkit.autonomy.freshness_sla_runner import tick
    rows = tick(now=time.time()) or []
    return {"rows": len(rows),
            "red": sum(1 for r in rows if str(r.get("status")).upper() == "RED")}


# (name, is_slow, callable-name-in-this-module). Looked up via getattr at call
# time -- like maintenance_templates -- so a test's monkeypatch.setattr is picked up.
_STEP_SPECS: List[Tuple[str, bool, str]] = [
    ("line_snapshot", True, "_step_line_snapshot"),
    ("settle_sweep", True, "_step_settle_sweep"),
    ("pnl_bestbets", False, "_step_pnl_bestbets"),
    ("analytics_verify", False, "_step_analytics_verify"),
    ("feed_health", True, "_step_feed_health"),
    ("freshness_sla", False, "_step_freshness_sla"),
]


def _log(line: str) -> None:
    # ponytail: stderr, not stdout -- the MCP server's run_burst tool calls
    # run_burst() in-process while stdout carries JSON-RPC framing; a stray
    # stdout print here desyncs that stream. Progress lines are diagnostics,
    # not data, so stderr is the correct channel for both callers (CLI + MCP).
    print(line, file=sys.stderr)
    sys.stderr.flush()


def run_burst(*, steps: Optional[List[str]] = None, skip_slow: bool = False,
              rss_limit_mb: float = RSS_LIMIT_MB, rss_fn: Callable[[], float] = _rss_mb,
              report_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the maintenance steps once, sequentially, exception-isolated.

    *steps* (names) restricts the run; *skip_slow* drops network steps. After
    each step RSS is checked against *rss_limit_mb*: cross it and the rest are
    skipped with an aborted_reason. Writes + returns the burst report.
    """
    want = set(steps) if steps else None
    report: Dict[str, Any] = {"started": _now_iso(), "steps": [],
                              "edge_claimed": False, "honest_note": _HONEST_NOTE}
    for name, slow, fnname in _STEP_SPECS:
        if want is not None and name not in want:
            continue
        if skip_slow and slow:
            report["steps"].append({"name": name, "status": "skipped_slow",
                                    "secs": 0.0, "rss_mb_after": round(rss_fn(), 1)})
            _log("[burst] %-18s status=skipped_slow" % name)
            continue
        rss_before = rss_fn()
        t0 = time.monotonic()
        try:
            getattr(sys.modules[__name__], fnname)()
            status = "ok"
        except Exception as exc:  # noqa: BLE001 -- one step must never kill the burst
            status = "error: %s" % str(exc)[:120]
        secs = round(time.monotonic() - t0, 2)
        rss_after = rss_fn()
        report["steps"].append({"name": name, "status": status, "secs": secs,
                                "rss_mb_after": round(rss_after, 1)})
        _log("[burst] %-18s status=%-8s secs=%7.2f rss=%.1fmb (%+.1f)"
             % (name, status.split(":")[0], secs, rss_after, rss_after - rss_before))
        if rss_after > rss_limit_mb:
            report["aborted_reason"] = ("rss_%.0fmb_exceeded_%.0fmb_cap"
                                        % (rss_after, rss_limit_mb))
            _log("[burst] ABORT %s -- skipping remaining steps" % report["aborted_reason"])
            break
    out = Path(report_path) if report_path else REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="ascii",
                   errors="replace")
    tmp.replace(out)
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="On-demand maintenance burst (fleet OFF).")
    ap.add_argument("--steps", default=None,
                    help="comma-separated subset (default: all): "
                         + ",".join(s[0] for s in _STEP_SPECS))
    ap.add_argument("--skip-slow", action="store_true", help="skip network steps")
    args = ap.parse_args(argv)
    steps = [s.strip() for s in args.steps.split(",")] if args.steps else None
    report = run_burst(steps=steps, skip_slow=args.skip_slow)
    _log("[burst] wrote %s (%d steps)" % (REPORT_PATH, len(report["steps"])))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
